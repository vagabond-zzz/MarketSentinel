from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import FeedStatus, SignalPriority
from market_sentinel.intelligence.compress import compress_intelligence_input, to_model_payload
from market_sentinel.intelligence.contract import (
    EpisodeCallBudget,
    FallbackReason,
    IntelligenceAnnotation,
    IntelligenceInput,
    IntelligenceResult,
    IntelligenceStatus,
)
from market_sentinel.intelligence.diagnostics import IntelligenceDiagnostics
from market_sentinel.intelligence.errors import (
    IntelligenceError,
    IntelligenceMalformedError,
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
)
from market_sentinel.intelligence.model_settings import DEFAULT_TIMEOUT_S
from market_sentinel.intelligence.provider import IntelligenceProvider
from market_sentinel.intelligence.redaction import redact_secrets
from market_sentinel.intelligence.registry import AnnotationRegistry
from market_sentinel.intelligence.router import RouterPolicy, need_intelligence
from market_sentinel.runtime.results import EngineTickResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntelligenceWork:
    signal_id: str
    payload: IntelligenceInput
    generation: int


_FALLBACK_STATUS = IntelligenceStatus.FALLBACK


def _reason_for(exc: BaseException) -> FallbackReason:
    if isinstance(exc, IntelligenceTimeoutError) or isinstance(exc, TimeoutError):
        return FallbackReason.TIMEOUT
    if isinstance(exc, IntelligenceMalformedError):
        return FallbackReason.MALFORMED
    if isinstance(exc, IntelligenceRateLimitError):
        return FallbackReason.RATE_LIMITED
    if isinstance(exc, IntelligenceError):
        return FallbackReason.UNAVAILABLE
    return FallbackReason.TRANSPORT


class IntelligenceCoordinator:
    """Async sidecar. MarketEngine.tick must not await this object's model calls."""

    def __init__(
        self,
        provider: IntelligenceProvider,
        clock: Clock,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        queue_size: int = 8,
        concurrency: int = 1,
        budget: EpisodeCallBudget | None = None,
        policy: RouterPolicy | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._timeout_s = timeout_s
        self._queue_size = queue_size
        self._concurrency = max(1, concurrency)
        self._budget = budget or EpisodeCallBudget()
        self._policy = policy or RouterPolicy()
        self._secrets = secrets
        self.registry = AnnotationRegistry()
        self.diagnostics = IntelligenceDiagnostics()
        self._queue: asyncio.Queue[IntelligenceWork | None] | None = None
        self._workers: list[asyncio.Task[None]] = []
        self._calls: dict[str, int] = {}
        self._last_priority: dict[str, SignalPriority] = {}
        self._generation: dict[str, int] = {}
        self._pending: dict[str, int] = {}
        self._active_ids: set[str] = set()
        self._in_flight_tasks: dict[str, asyncio.Task[object]] = {}
        self._in_flight = 0
        self._closed = False
        self._idle = asyncio.Event()
        self._idle.set()

    def tracked_episode_count(self) -> int:
        return len(
            set(self._calls) | set(self._generation) | set(self._last_priority) | set(self._pending)
        )

    async def start(self) -> None:
        if self._queue is not None:
            return
        self._closed = False
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        self._workers = [
            asyncio.create_task(self._worker(), name=f"intel-worker-{index}")
            for index in range(self._concurrency)
        ]

    async def shutdown(self) -> None:
        queue = self._queue
        if queue is None:
            self._reset_runtime_state_after_shutdown()
            return
        self._closed = True
        for task in self._in_flight_tasks.values():
            if not task.done():
                task.cancel()
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers = []
        self._queue = None
        self._reset_runtime_state_after_shutdown()

    def _reset_runtime_state_after_shutdown(self) -> None:
        """Drop episode lifecycle maps. Diagnostics counters are left intact."""
        self._calls.clear()
        self._last_priority.clear()
        self._generation.clear()
        self._pending.clear()
        self._active_ids.clear()
        self._in_flight_tasks.clear()
        self._in_flight = 0
        self.registry.clear()
        self._idle.set()

    async def idle(self) -> None:
        queue = self._queue
        if queue is None:
            return
        await queue.join()
        while self._in_flight > 0:
            await asyncio.sleep(0)

    def observe_tick(
        self,
        result: EngineTickResult,
        *,
        feed_status_for: Callable[[str], FeedStatus],
        active_ids: set[str] | None = None,
    ) -> None:
        started = self._clock.monotonic_time()
        current_active: set[str] = set(active_ids) if active_ids is not None else set()
        if active_ids is None:
            for row in result.symbol_results:
                current_active.update(signal.id for signal in row.signal_updates)
        now = self._clock.wall_time()
        for row in result.symbol_results:
            for signal in row.signal_updates:
                if signal.expires_at is not None and now >= signal.expires_at:
                    current_active.discard(signal.id)
        self._retire_inactive(current_active)
        for row in result.symbol_results:
            feed = feed_status_for(row.symbol)
            traces = {item.signal_id: item for item in row.traces}
            alerts = {item.id for item in row.alert_candidates}
            for signal in row.signal_updates:
                trace = traces.get(signal.id)
                if trace is None:
                    continue
                expired = signal.id not in current_active
                payload = compress_intelligence_input(
                    signal=signal,
                    trace=trace,
                    feed_status=feed,
                    alert_edge=signal.id in alerts,
                    episode_call_count=self._calls.get(signal.id, 0),
                    last_requested_priority=self._last_priority.get(signal.id),
                    expired=expired,
                )
                decision = need_intelligence(payload, policy=self._policy, budget=self._budget)
                self.diagnostics.router_decisions += 1
                if not decision.requested:
                    self.diagnostics.requests_suppressed += 1
                    continue
                self._enqueue(payload)
        elapsed = self._clock.monotonic_time() - started
        self.diagnostics.router_decision_latency_s += elapsed
        self.diagnostics.router_latencies.append(elapsed)
        if self._queue is not None:
            self.diagnostics.queue_depth = self._queue.qsize()

    def _retire_inactive(self, active_ids: set[str]) -> None:
        self._active_ids = set(active_ids)
        self.registry.prune(self._active_ids)
        tracked = (
            set(self._calls)
            | set(self._generation)
            | set(self._last_priority)
            | set(self._pending)
            | self.registry.ids()
        )
        for signal_id in tracked - self._active_ids:
            self._invalidate(signal_id)

    def _invalidate(self, signal_id: str) -> None:
        self._generation[signal_id] = self._generation.get(signal_id, 0) + 1
        self.registry.drop(signal_id)
        self._cancel_in_flight(signal_id)
        self._maybe_forget(signal_id)

    def _cancel_in_flight(self, signal_id: str) -> None:
        task = self._in_flight_tasks.get(signal_id)
        if task is not None and not task.done():
            task.cancel()

    def _work_is_live(self, work: IntelligenceWork) -> bool:
        if work.signal_id not in self._active_ids:
            return False
        return work.generation == self._generation.get(work.signal_id)

    def _store(self, work: IntelligenceWork, result: IntelligenceResult) -> None:
        if not self._work_is_live(work):
            return
        self.registry.put(result)

    def _release_pending(self, signal_id: str) -> None:
        remaining = self._pending.get(signal_id, 0) - 1
        if remaining <= 0:
            self._pending.pop(signal_id, None)
        else:
            self._pending[signal_id] = remaining
        self._maybe_forget(signal_id)

    def _maybe_forget(self, signal_id: str) -> None:
        if signal_id in self._active_ids:
            return
        if self._pending.get(signal_id, 0) > 0:
            return
        self._calls.pop(signal_id, None)
        self._last_priority.pop(signal_id, None)
        self._generation.pop(signal_id, None)
        self._pending.pop(signal_id, None)

    def _enqueue(self, payload: IntelligenceInput) -> None:
        if self._queue is None:
            return
        work = IntelligenceWork(
            signal_id=payload.signal_id,
            payload=payload,
            generation=self._generation.get(payload.signal_id, 0) + 1,
        )
        try:
            self._queue.put_nowait(work)
        except asyncio.QueueFull:
            self.diagnostics.dropped_backpressure += 1
            logger.warning("intelligence queue full; dropping %s", payload.signal_id)
            return
        self._generation[payload.signal_id] = work.generation
        self._calls[payload.signal_id] = self._calls.get(payload.signal_id, 0) + 1
        self._last_priority[payload.signal_id] = payload.priority
        self._pending[payload.signal_id] = self._pending.get(payload.signal_id, 0) + 1
        self.diagnostics.requests_submitted += 1
        self._idle.clear()
        self.registry.put(
            IntelligenceResult(
                signal_id=payload.signal_id,
                status=IntelligenceStatus.QUEUED,
                requested=True,
                annotation=None,
                fallback_reason=FallbackReason.NONE,
                model_calls=self._calls[payload.signal_id],
            )
        )

    async def _worker(self) -> None:
        assert self._queue is not None
        queue = self._queue
        while True:
            work = await queue.get()
            try:
                if work is None:
                    return
                await self._run(work)
            finally:
                queue.task_done()

    async def _run(self, work: IntelligenceWork) -> None:
        try:
            await self._execute(work)
        finally:
            self._release_pending(work.signal_id)

    async def _execute(self, work: IntelligenceWork) -> None:
        if not self._work_is_live(work):
            self.diagnostics.stale_discard += 1
            return
        call: asyncio.Task[object] = asyncio.create_task(
            self._provider.complete(to_model_payload(work.payload), timeout_s=self._timeout_s)
        )
        self._in_flight_tasks[work.signal_id] = call
        if not self._work_is_live(work):
            self._cancel_in_flight(work.signal_id)
            self._in_flight_tasks.pop(work.signal_id, None)
            call.cancel()
            try:
                await call
            except (asyncio.CancelledError, Exception):
                pass
            self.diagnostics.stale_discard += 1
            return
        self._in_flight += 1
        self.diagnostics.model_calls += 1
        self._store(
            work,
            IntelligenceResult(
                signal_id=work.signal_id,
                status=IntelligenceStatus.RUNNING,
                requested=True,
                annotation=None,
                fallback_reason=FallbackReason.NONE,
                model_calls=self._calls.get(work.signal_id, 0),
            ),
        )
        started = self._clock.monotonic_time()
        try:
            try:
                completion = await asyncio.wait_for(call, timeout=self._timeout_s)
            except asyncio.CancelledError:
                if self._closed:
                    raise
                self.diagnostics.stale_discard += 1
                return
            elapsed = self._clock.monotonic_time() - started
            self.diagnostics.model_latency_s += elapsed
            self.diagnostics.model_latencies.append(elapsed)
            if not self._work_is_live(work):
                self.diagnostics.stale_discard += 1
                return
            parse_s = float(getattr(self._provider, "last_parse_latency_s", 0.0) or 0.0)
            self.diagnostics.parse_latency_s += parse_s
            annotation = IntelligenceAnnotation(
                signal_id=work.signal_id,
                worth_highlight=completion.worth_highlight,
                reason=completion.reason,
                confidence=completion.confidence,
                summary=completion.summary,
                created_timestamp=self._clock.wall_time(),
            )
            self._store(
                work,
                IntelligenceResult(
                    signal_id=work.signal_id,
                    status=IntelligenceStatus.ENRICHED,
                    requested=True,
                    annotation=annotation,
                    fallback_reason=FallbackReason.NONE,
                    model_calls=self._calls.get(work.signal_id, 0),
                    model_latency_s=elapsed,
                ),
            )
        except Exception as exc:
            elapsed = self._clock.monotonic_time() - started
            self.diagnostics.model_latency_s += elapsed
            self.diagnostics.model_latencies.append(elapsed)
            reason = _reason_for(exc)
            self.diagnostics.fallback_count += 1
            if reason is FallbackReason.TIMEOUT:
                self.diagnostics.timeout_count += 1
            elif reason is FallbackReason.MALFORMED:
                self.diagnostics.parse_failure_count += 1
            elif reason is FallbackReason.RATE_LIMITED:
                self.diagnostics.rate_limit_count += 1
            logger.warning(
                "intelligence fallback signal=%s reason=%s detail=%s",
                work.signal_id,
                reason.value,
                redact_secrets(str(exc), self._secrets),
            )
            if self._work_is_live(work):
                self._store(
                    work,
                    IntelligenceResult(
                        signal_id=work.signal_id,
                        status=_FALLBACK_STATUS,
                        requested=True,
                        annotation=None,
                        fallback_reason=reason,
                        model_calls=self._calls.get(work.signal_id, 0),
                        model_latency_s=elapsed,
                    ),
                )
            else:
                self.diagnostics.stale_discard += 1
        finally:
            self._in_flight_tasks.pop(work.signal_id, None)
            self._in_flight = max(0, self._in_flight - 1)
            if self._queue is not None and self._queue.empty() and self._in_flight == 0:
                self._idle.set()

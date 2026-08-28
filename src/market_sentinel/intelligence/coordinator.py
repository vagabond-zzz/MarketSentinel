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
from market_sentinel.intelligence.provider import IntelligenceProvider
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
        timeout_s: float = 8.0,
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
        self._in_flight = 0
        self._idle = asyncio.Event()
        self._idle.set()

    async def start(self) -> None:
        if self._queue is not None:
            return
        self._queue = asyncio.Queue(maxsize=self._queue_size)
        self._workers = [
            asyncio.create_task(self._worker(), name=f"intel-worker-{index}")
            for index in range(self._concurrency)
        ]

    async def shutdown(self) -> None:
        queue = self._queue
        if queue is None:
            return
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._workers = []
        self._queue = None

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
        live_ids: set[str] = set()
        for row in result.symbol_results:
            feed = feed_status_for(row.symbol)
            traces = {item.signal_id: item for item in row.traces}
            alerts = {item.id for item in row.alert_candidates}
            for signal in row.signal_updates:
                live_ids.add(signal.id)
                trace = traces.get(signal.id)
                if trace is None:
                    continue
                payload = compress_intelligence_input(
                    signal=signal,
                    trace=trace,
                    feed_status=feed,
                    alert_edge=signal.id in alerts,
                    episode_call_count=self._calls.get(signal.id, 0),
                    last_requested_priority=self._last_priority.get(signal.id),
                    expired=False,
                )
                decision = need_intelligence(payload, policy=self._policy, budget=self._budget)
                self.diagnostics.router_decisions += 1
                if not decision.requested:
                    self.diagnostics.requests_suppressed += 1
                    continue
                self._enqueue(payload)
        self.registry.prune(active_ids if active_ids is not None else live_ids)
        elapsed = self._clock.monotonic_time() - started
        self.diagnostics.router_decision_latency_s += elapsed
        self.diagnostics.router_latencies.append(elapsed)
        if self._queue is not None:
            self.diagnostics.queue_depth = self._queue.qsize()

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
        if work.generation != self._generation.get(work.signal_id, 0):
            self.diagnostics.stale_discard += 1
            return
        self._in_flight += 1
        self.registry.put(
            IntelligenceResult(
                signal_id=work.signal_id,
                status=IntelligenceStatus.RUNNING,
                requested=True,
                annotation=None,
                fallback_reason=FallbackReason.NONE,
                model_calls=self._calls.get(work.signal_id, 0),
            )
        )
        self.diagnostics.model_calls += 1
        started = self._clock.monotonic_time()
        try:
            completion = await asyncio.wait_for(
                self._provider.complete(to_model_payload(work.payload), timeout_s=self._timeout_s),
                timeout=self._timeout_s,
            )
            elapsed = self._clock.monotonic_time() - started
            self.diagnostics.model_latency_s += elapsed
            self.diagnostics.model_latencies.append(elapsed)
            annotation = IntelligenceAnnotation(
                signal_id=work.signal_id,
                worth_highlight=completion.worth_highlight,
                reason=completion.reason,
                confidence=completion.confidence,
                summary=completion.summary,
                created_timestamp=self._clock.wall_time(),
            )
            self.registry.put(
                IntelligenceResult(
                    signal_id=work.signal_id,
                    status=IntelligenceStatus.ENRICHED,
                    requested=True,
                    annotation=annotation,
                    fallback_reason=FallbackReason.NONE,
                    model_calls=self._calls.get(work.signal_id, 0),
                    model_latency_s=elapsed,
                )
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
                "intelligence fallback signal=%s reason=%s",
                work.signal_id,
                reason.value,
            )
            del exc
            self.registry.put(
                IntelligenceResult(
                    signal_id=work.signal_id,
                    status=_FALLBACK_STATUS,
                    requested=True,
                    annotation=None,
                    fallback_reason=reason,
                    model_calls=self._calls.get(work.signal_id, 0),
                    model_latency_s=elapsed,
                )
            )
        finally:
            self._in_flight = max(0, self._in_flight - 1)
            if self._queue is not None and self._queue.empty() and self._in_flight == 0:
                self._idle.set()

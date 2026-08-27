from __future__ import annotations

import logging
from dataclasses import dataclass

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.domain.signals import SignalPipelineResult
from market_sentinel.features.engine import FeatureEngine
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.orchestration.warming import WarmingPolicy
from market_sentinel.providers.base import MarketProvider
from market_sentinel.runtime.results import EngineTickResult, SymbolTickResult
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.watchlist.watchlist import Watchlist

logger = logging.getLogger(__name__)


@dataclass
class EngineDiagnostics:
    out_of_order_count: int = 0
    duplicate_timestamp_count: int = 0
    recovery_count: int = 0
    last_fetch_error: str | None = None


class MarketEngine:
    def __init__(
        self,
        *,
        clock: Clock,
        watchlist: Watchlist,
        provider: MarketProvider,
        scheduler: AdaptiveScheduler,
        buffers: SymbolBuffers,
        states: MarketStateStore,
        health: FeedHealthTracker,
        feature_engine: FeatureEngine | None = None,
        pipeline: SignalPipeline | None = None,
        warming: WarmingPolicy | None = None,
    ) -> None:
        self.clock = clock
        self.watchlist = watchlist
        self.provider = provider
        self.scheduler = scheduler
        self.buffers = buffers
        self.states = states
        self.health = health
        self._feature_engine = feature_engine or FeatureEngine()
        self.pipeline = pipeline or SignalPipeline(clock)
        self._warming = warming or WarmingPolicy()
        self._fetched_symbols: set[str] = set()
        self.diagnostics = EngineDiagnostics()

    async def tick(self) -> EngineTickResult:
        enabled = self.watchlist.enabled_symbols()
        due = self.scheduler.due_symbols(enabled)
        self._fetched_symbols = set()
        if due:
            await self._fetch_due(due)
        due_set = set(due)
        results: list[SymbolTickResult] = []
        for symbol in due:
            results.append(self._process_symbol(symbol))
        for symbol in enabled:
            if symbol not in due_set:
                self._project_health(symbol)
        return EngineTickResult(symbol_results=tuple(results))

    async def _fetch_due(self, due: list[str]) -> None:
        try:
            snapshots = await self.provider.fetch_quotes(due)
        except Exception as exc:
            logger.warning("provider fetch failed: %s", exc)
            self.diagnostics.last_fetch_error = type(exc).__name__
            for symbol in due:
                self.health.observe(symbol, error=exc)
                self.scheduler.mark_fetched(symbol)
            return

        self.diagnostics.last_fetch_error = None
        found = {item.symbol: item for item in snapshots}
        for symbol in due:
            snapshot = found.get(symbol)
            if snapshot is None:
                self.health.observe(symbol, error=RuntimeError("missing quote"))
            else:
                self._ingest_snapshot(symbol, snapshot)
            self.scheduler.mark_fetched(symbol)

    def _ingest_snapshot(self, symbol: str, snapshot: MarketSnapshot) -> None:
        previous_status = self.health.peek_status(symbol)
        latest = self.buffers.latest(symbol)
        if latest is not None and snapshot.market_timestamp < latest.market_timestamp:
            self.diagnostics.out_of_order_count += 1
            if self.diagnostics.out_of_order_count == 1:
                logger.warning(
                    "suppressing older quote %s market_ts=%s latest=%s",
                    symbol,
                    snapshot.market_timestamp,
                    latest.market_timestamp,
                )
            self.health.observe(symbol, snapshot)
            return
        if latest is not None and snapshot.market_timestamp == latest.market_timestamp:
            self.diagnostics.duplicate_timestamp_count += 1
        self.buffers.append(snapshot)
        self.states.update_latest(snapshot)
        self.health.observe(symbol, snapshot)
        after = self.health.peek_status(symbol)
        if previous_status in {FeedStatus.STALE, FeedStatus.DISCONNECTED} and after in {
            FeedStatus.LIVE,
            FeedStatus.DELAYED,
        }:
            self.diagnostics.recovery_count += 1
        self._fetched_symbols.add(symbol)

    def _process_symbol(self, symbol: str) -> SymbolTickResult:
        level_before = self.scheduler.get_level(symbol)
        stage = "init"
        try:
            if symbol not in self._fetched_symbols:
                self._project_health(symbol)
                current = self.states.get(symbol)
                return self._tick_result(
                    symbol,
                    level_before=level_before,
                    features=current.features if current is not None else None,
                    pipeline=SignalPipelineResult((), (), (), ()),
                )
            stage = "features"
            buffer = self.buffers.buffer(symbol)
            if buffer is None:
                self._project_health(symbol)
                return self._tick_result(
                    symbol,
                    level_before=level_before,
                    features=None,
                    pipeline=SignalPipelineResult((), (), (), ()),
                )

            features = self._feature_engine.compute(buffer)
            stage = "pipeline"
            current_state = self.states.get(symbol)
            previous = current_state.features if current_state is not None else None
            if features is None:
                pipeline_result = SignalPipelineResult((), (), (), ())
            else:
                pipeline_result = self.pipeline.process(previous, features)

            stage = "warming"
            request = self._warming.request(symbol, features, pipeline_result.accepted_events)
            self.scheduler.set_level(symbol, request.level)
            level_after = self.scheduler.get_level(symbol)

            stage = "state"
            self.states.apply_runtime(
                symbol,
                level=level_after,
                feed_status=self.health.status(symbol),
                feed_latency=self.health.feed_latency(symbol),
                last_update_age=self.health.last_update_age(symbol),
                features=features,
                active_signals=pipeline_result.signal_updates,
            )
            return SymbolTickResult(
                symbol=symbol,
                features=features,
                accepted_events=pipeline_result.accepted_events,
                signal_updates=pipeline_result.signal_updates,
                traces=pipeline_result.traces,
                alert_candidates=pipeline_result.alert_candidates,
                level_before=level_before,
                level_after=level_after,
            )
        except Exception:
            logger.exception("symbol %s failed at stage %s", symbol, stage)
            self._project_health(symbol)
            current = self.states.get(symbol)
            return self._tick_result(
                symbol,
                level_before=level_before,
                features=current.features if current is not None else None,
                pipeline=SignalPipelineResult((), (), (), ()),
            )

    def _project_health(self, symbol: str) -> None:
        self.states.apply_runtime(
            symbol,
            level=self.scheduler.get_level(symbol),
            feed_status=self.health.status(symbol),
            feed_latency=self.health.feed_latency(symbol),
            last_update_age=self.health.last_update_age(symbol),
        )

    def _tick_result(
        self,
        symbol: str,
        *,
        level_before: SchedulerLevel,
        features: MarketFeatures | None,
        pipeline: SignalPipelineResult,
    ) -> SymbolTickResult:
        return SymbolTickResult(
            symbol=symbol,
            features=features,
            accepted_events=pipeline.accepted_events,
            signal_updates=pipeline.signal_updates,
            traces=pipeline.traces,
            alert_candidates=pipeline.alert_candidates,
            level_before=level_before,
            level_after=self.scheduler.get_level(symbol),
        )

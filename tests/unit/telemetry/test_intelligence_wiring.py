from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit.events.helpers import make_features
from tests.unit.test_runtime_pipeline import ScriptedFeatureEngine, _quote

from market_sentinel.clock import FakeClock
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.errors import IntelligenceTimeoutError
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.parse import ModelCompletion
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.contract import DecisionReason, LatencyStage, TelemetryName
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.watchlist.watchlist import Watchlist


def _engine(
    tmp_path: Path,
    clock: FakeClock,
    coordinator: IntelligenceCoordinator,
    runtime: TelemetryRuntime,
    features: list[MarketFeatures],
) -> tuple[FakeProvider, MarketEngine]:
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add("00700.HK")
    provider = FakeProvider(clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(cold_interval_s=0.0, warm_interval_s=0.0, hot_interval_s=0.0),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        feature_engine=ScriptedFeatureEngine({"00700.HK": features}),  # type: ignore[arg-type]
        pipeline=SignalPipeline(clock, telemetry=runtime),
        intelligence=coordinator,
        telemetry=runtime,
    )
    return provider, engine


@pytest.mark.asyncio
async def test_router_no_emits_decision_reason(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    memory = InMemoryTelemetryCollector()
    runtime = TelemetryRuntime(clock, memory)
    coordinator = IntelligenceCoordinator(FakeIntelligenceProvider(), clock, telemetry=runtime)
    await coordinator.start()
    ts = clock.wall_time()
    features = [
        make_features(market_timestamp=ts, session_high_ref=100.0, session_high_obs=100.0),
        make_features(
            market_timestamp=ts + 10.0,
            change_1m=0.006,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
    ]
    quotes, engine = _engine(tmp_path, clock, coordinator, runtime, features)
    _quote(quotes, clock, "00700.HK", 100.0)
    await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.6)
    await engine.tick()
    skipped = [item for item in memory.events if item.name is TelemetryName.INTELLIGENCE_SKIPPED]
    assert skipped
    assert skipped[0].decision_reason is DecisionReason.NOT_CANDIDATE
    assert skipped[0].fallback_reason is None
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_provider_fallback_and_no_token_usage(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    memory = InMemoryTelemetryCollector()
    runtime = TelemetryRuntime(clock, memory)
    provider = FakeIntelligenceProvider(error=IntelligenceTimeoutError("slow"))
    coordinator = IntelligenceCoordinator(provider, clock, timeout_s=0.05, telemetry=runtime)
    await coordinator.start()
    ts = clock.wall_time()
    features = [
        make_features(market_timestamp=ts, session_high_ref=100.0, session_high_obs=100.0),
        make_features(
            market_timestamp=ts + 10.0,
            change_1m=0.006,
            volume_ratio_5m=1.8,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
    ]
    quotes, engine = _engine(tmp_path, clock, coordinator, runtime, features)
    _quote(quotes, clock, "00700.HK", 100.0)
    await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.6)
    await engine.tick()
    await coordinator.idle()
    fallback = [item for item in memory.events if item.name is TelemetryName.INTELLIGENCE_FALLBACK]
    assert fallback
    assert fallback[0].fallback_reason == "timeout"
    assert fallback[0].decision_reason is None
    assert not any(item.name is TelemetryName.INTELLIGENCE_TOKEN_USAGE for item in memory.events)
    stages = {
        item.latency_stage
        for item in memory.events
        if item.name is TelemetryName.INTELLIGENCE_LATENCY
    }
    assert LatencyStage.ROUTER in stages
    assert LatencyStage.MODEL in stages
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_actual_token_usage_is_emitted(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    memory = InMemoryTelemetryCollector()
    runtime = TelemetryRuntime(clock, memory)
    provider = FakeIntelligenceProvider(
        ModelCompletion(
            worth_highlight=True,
            reason="tape expanded",
            confidence=0.6,
            summary="volume and price moved together",
            token_in=11,
            token_out=7,
        )
    )
    coordinator = IntelligenceCoordinator(provider, clock, telemetry=runtime)
    await coordinator.start()
    ts = clock.wall_time()
    features = [
        make_features(market_timestamp=ts, session_high_ref=100.0, session_high_obs=100.0),
        make_features(
            market_timestamp=ts + 10.0,
            change_1m=0.006,
            volume_ratio_5m=1.8,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
    ]
    quotes, engine = _engine(tmp_path, clock, coordinator, runtime, features)
    _quote(quotes, clock, "00700.HK", 100.0)
    await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.6)
    await engine.tick()
    await coordinator.idle()
    usage = [item for item in memory.events if item.name is TelemetryName.INTELLIGENCE_TOKEN_USAGE]
    assert len(usage) == 1
    assert usage[0].token_in == 11
    assert usage[0].token_out == 7
    await coordinator.shutdown()

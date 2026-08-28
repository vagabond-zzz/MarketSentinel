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
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


def _important_features(ts: float) -> list[MarketFeatures | BaseException]:
    return [
        make_features(market_timestamp=ts, session_high_ref=100.0, session_high_obs=100.0),
        make_features(
            market_timestamp=ts + 10.0,
            change_1m=0.006,
            volume_ratio_5m=1.8,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
    ]


def _engine(
    tmp_path: Path,
    clock: FakeClock,
    coordinator: IntelligenceCoordinator,
    features: list[MarketFeatures | BaseException],
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
        intelligence=coordinator,
    )
    return provider, engine


@pytest.mark.asyncio
async def test_slow_model_does_not_block_market_ticks(tmp_path: Path) -> None:
    provider = FakeIntelligenceProvider(delay_s=0.15)
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    coordinator = IntelligenceCoordinator(provider, clock, timeout_s=2.0)
    await coordinator.start()
    ts = clock.wall_time()
    features = [
        *_important_features(ts),
        *[
            make_features(
                market_timestamp=ts + 20.0 + index,
                change_1m=0.006,
                volume_ratio_5m=1.8,
                session_high_ref=100.0,
                session_high_obs=100.0,
            )
            for index in range(8)
        ],
    ]
    quotes, engine = _engine(tmp_path, clock, coordinator, features)
    _quote(quotes, clock, "00700.HK", 100.0)
    first = await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.6)
    second = await engine.tick()
    extra = 0
    for _ in range(4):
        clock.advance_wall(1.0)
        _quote(quotes, clock, "00700.HK", 100.6)
        await engine.tick()
        extra += 1
    assert first.for_symbol("00700.HK") is not None
    assert second.for_symbol("00700.HK") is not None
    assert extra == 4
    await coordinator.idle()
    assert provider.calls
    assert coordinator.diagnostics.model_calls == 1
    signal = engine.states.get("00700.HK")
    assert signal is not None and signal.active_signals
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_model_timeout_keeps_rule_signal(tmp_path: Path) -> None:
    model = FakeIntelligenceProvider(error=IntelligenceTimeoutError("timeout"))
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    coordinator = IntelligenceCoordinator(model, clock, timeout_s=0.05)
    await coordinator.start()
    features = _important_features(clock.wall_time())
    quotes, engine = _engine(tmp_path, clock, coordinator, features)
    _quote(quotes, clock, "00700.HK", 100.0)
    await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.6)
    result = await engine.tick()
    await coordinator.idle()
    row = result.for_symbol("00700.HK")
    assert row is not None
    assert row.alert_candidates
    signal_id = row.alert_candidates[0].id
    state = engine.states.get("00700.HK")
    assert state is not None
    assert any(item.id == signal_id for item in state.active_signals)
    stored = coordinator.registry.get(signal_id)
    assert stored is not None
    assert stored.annotation is None
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_same_episode_makes_one_model_call(tmp_path: Path) -> None:
    model = FakeIntelligenceProvider(delay_s=0.05)
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    coordinator = IntelligenceCoordinator(model, clock)
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
        make_features(
            market_timestamp=ts + 20.0,
            change_1m=0.006,
            volume_ratio_5m=1.8,
            session_high_ref=100.0,
            session_high_obs=100.1,
        ),
    ]
    quotes, engine = _engine(tmp_path, clock, coordinator, features)
    _quote(quotes, clock, "00700.HK", 100.0)
    await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.6)
    first = await engine.tick()
    clock.advance_wall(10.0)
    _quote(quotes, clock, "00700.HK", 100.7)
    second = await engine.tick()
    await coordinator.idle()
    row1 = first.for_symbol("00700.HK")
    row2 = second.for_symbol("00700.HK")
    assert row1 is not None and row2 is not None
    assert row1.alert_candidates
    assert coordinator.diagnostics.model_calls == 1
    assert len(model.calls) == 1
    await coordinator.shutdown()

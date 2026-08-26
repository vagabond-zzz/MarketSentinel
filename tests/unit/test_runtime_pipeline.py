from __future__ import annotations

import logging
from pathlib import Path

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventDirection, EventType, SchedulerLevel, SignalPriority
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.features.engine import FeatureEngine
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.ring_buffer import RingBuffer
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.watchlist.watchlist import Watchlist
from tests.unit.events.helpers import make_features


class ScriptedFeatureEngine:
    def __init__(self, queues: dict[str, list[MarketFeatures | BaseException]]) -> None:
        self._queues = queues

    def compute(self, buffer: RingBuffer) -> MarketFeatures | None:
        latest = buffer.latest()
        assert latest is not None
        item = self._queues[latest.symbol].pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class ExplodingPipeline(SignalPipeline):
    def process(self, previous: MarketFeatures | None, current: MarketFeatures):
        if current.symbol == "000001.SZ":
            raise RuntimeError("pipeline boom")
        return super().process(previous, current)


def _engine(
    tmp_path: Path,
    *,
    feature_engine: FeatureEngine | ScriptedFeatureEngine | None = None,
    pipeline: SignalPipeline | None = None,
    dwell: bool = True,
) -> tuple[FakeClock, FakeProvider, MarketEngine]:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    provider = FakeProvider(clock)
    policy = SchedulerPolicy(
        cold_interval_s=0.0,
        warm_interval_s=0.0,
        hot_interval_s=0.0,
        hot_downgrade_dwell_s=30.0 if dwell else 0.0,
        warm_downgrade_dwell_s=60.0 if dwell else 0.0,
    )
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock, policy),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        feature_engine=feature_engine,  # type: ignore[arg-type]
        pipeline=pipeline,
    )
    return clock, provider, engine


def _quote(
    provider: FakeProvider,
    clock: FakeClock,
    symbol: str,
    price: float,
    *,
    high: float | None = None,
    low: float | None = None,
    volume: float = 0.0,
) -> None:
    high = price if high is None else high
    low = price if low is None else low
    provider.set_quote(
        symbol,
        price=price,
        open=100.0,
        high=high,
        low=low,
        prev_close=100.0,
        volume=volume,
        market_timestamp=clock.wall_time(),
    )


async def _tick_quote(
    clock: FakeClock,
    provider: FakeProvider,
    engine: MarketEngine,
    symbol: str,
    price: float,
    **kwargs: float,
):
    _quote(provider, clock, symbol, price, **kwargs)
    return await engine.tick()


async def test_full_tick_projects_snapshot_features_events_signal_and_state(
    tmp_path: Path,
) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(60.0)
    result = await _tick_quote(clock, provider, engine, "00700.HK", 100.8, high=100.8)
    row = result.for_symbol("00700.HK")
    assert row is not None
    assert row.features is not None
    assert row.features.change_1m == pytest.approx(0.008)
    assert row.accepted_events
    assert any(item.type is EventType.RAPID_MOVE for item in row.accepted_events)
    assert row.signal_updates
    assert row.alert_candidates
    assert row.traces
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.latest is not None
    assert state.latest.price == 100.8
    assert state.features is row.features
    assert state.active_signals == row.signal_updates
    assert state.level is SchedulerLevel.HOT
    assert row.level_before is SchedulerLevel.COLD
    assert row.level_after is SchedulerLevel.HOT


async def test_alert_candidates_are_edge_triggered(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(60.0)
    first = await _tick_quote(clock, provider, engine, "00700.HK", 100.8, high=100.8)
    row1 = first.for_symbol("00700.HK")
    assert row1 is not None
    assert row1.alert_candidates
    signal_id = row1.alert_candidates[0].id
    clock.advance_wall(1.0)
    second = await _tick_quote(clock, provider, engine, "00700.HK", 100.8, high=100.8)
    row2 = second.for_symbol("00700.HK")
    assert row2 is not None
    assert row2.alert_candidates == ()
    state = engine.states.get("00700.HK")
    assert state is not None
    assert any(item.id == signal_id for item in state.active_signals)


async def test_cooldown_suppresses_alert_but_updates_active_state(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
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
    _, provider, engine = _engine(
        tmp_path,
        feature_engine=ScriptedFeatureEngine({"00700.HK": list(features)}),
    )
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(10.0)
    first = await _tick_quote(clock, provider, engine, "00700.HK", 100.6)
    row1 = first.for_symbol("00700.HK")
    assert row1 is not None
    assert row1.alert_candidates[0].priority is SignalPriority.IMPORTANT
    signal_id = row1.alert_candidates[0].id
    clock.advance_wall(10.0)
    second = await _tick_quote(clock, provider, engine, "00700.HK", 100.6, high=100.1)
    row2 = second.for_symbol("00700.HK")
    assert row2 is not None
    assert any(item.type is EventType.DAY_HIGH_BREAKOUT for item in row2.accepted_events)
    assert row2.alert_candidates == ()
    updated = row2.signal_updates[0]
    assert updated.id == signal_id
    assert updated.priority is SignalPriority.IMPORTANT
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.active_signals[0].id == signal_id
    assert state.active_signals[0].event_ids == updated.event_ids


async def test_new_episode_after_expiry_gets_first_alert(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(60.0)
    first = await _tick_quote(clock, provider, engine, "00700.HK", 100.8, high=100.8)
    row1 = first.for_symbol("00700.HK")
    assert row1 is not None
    first_id = row1.alert_candidates[0].id
    clock.advance_wall(91.0)
    quiet = await _tick_quote(clock, provider, engine, "00700.HK", 100.8, high=100.8)
    quiet_row = quiet.for_symbol("00700.HK")
    assert quiet_row is not None
    assert quiet_row.alert_candidates == ()
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.active_signals == ()
    clock.advance_wall(60.0)
    second = await _tick_quote(clock, provider, engine, "00700.HK", 101.6, high=101.6)
    row2 = second.for_symbol("00700.HK")
    assert row2 is not None
    assert len(row2.alert_candidates) == 1
    assert row2.alert_candidates[0].id != first_id
    assert row2.alert_candidates[0].family == row1.alert_candidates[0].family


async def test_reversal_creates_independent_episode_alert(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(60.0)
    up = await _tick_quote(clock, provider, engine, "00700.HK", 100.8, high=100.8)
    up_row = up.for_symbol("00700.HK")
    assert up_row is not None
    up_id = up_row.alert_candidates[0].id
    clock.advance_wall(10.0)
    down = await _tick_quote(clock, provider, engine, "00700.HK", 99.2, low=99.2)
    down_row = down.for_symbol("00700.HK")
    assert down_row is not None
    assert len(down_row.alert_candidates) == 1
    down_id = down_row.alert_candidates[0].id
    assert down_id != up_id
    assert down_row.alert_candidates[0].direction is EventDirection.DOWN
    live_ids = {item.id for item in down_row.signal_updates}
    assert up_id in live_ids
    assert down_id in live_ids


async def test_none_event_is_not_copied_into_up_and_down_signals(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    ts = clock.wall_time()
    features = [
        make_features(market_timestamp=ts, session_high_ref=100.0, session_high_obs=100.0),
        make_features(
            market_timestamp=ts + 10.0,
            change_1m=0.006,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
        make_features(
            market_timestamp=ts + 20.0,
            change_1m=-0.006,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
        make_features(
            market_timestamp=ts + 30.0,
            volume_ratio_5m=1.8,
            session_high_ref=100.0,
            session_high_obs=100.0,
        ),
    ]
    _, provider, engine = _engine(
        tmp_path,
        feature_engine=ScriptedFeatureEngine({"00700.HK": list(features)}),
    )
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(10.0)
    await _tick_quote(clock, provider, engine, "00700.HK", 100.6)
    clock.advance_wall(10.0)
    await _tick_quote(clock, provider, engine, "00700.HK", 99.4)
    clock.advance_wall(10.0)
    result = await _tick_quote(clock, provider, engine, "00700.HK", 99.4)
    row = result.for_symbol("00700.HK")
    assert row is not None
    volume_events = [item for item in row.accepted_events if item.type is EventType.VOLUME_SPIKE]
    assert len(volume_events) == 1
    volume_id = volume_events[0].id
    homes = [signal for signal in row.signal_updates if volume_id in signal.event_ids]
    assert len(homes) == 1
    assert homes[0].direction is EventDirection.NONE
    directions = {item.direction for item in row.signal_updates}
    assert EventDirection.UP in directions
    assert EventDirection.DOWN in directions
    assert EventDirection.NONE in directions


async def test_warming_cold_warm_hot_and_cooldown_keeps_hot(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    cold = await _tick_quote(clock, provider, engine, "00700.HK", 100.0, high=100.4)
    assert cold.for_symbol("00700.HK") is not None
    assert engine.states.get("00700.HK") is not None
    assert engine.states.get("00700.HK").level is SchedulerLevel.COLD  # type: ignore[union-attr]

    clock.advance_wall(60.0)
    warm = await _tick_quote(clock, provider, engine, "00700.HK", 100.4, high=100.4)
    warm_row = warm.for_symbol("00700.HK")
    assert warm_row is not None
    assert warm_row.level_after is SchedulerLevel.WARM
    assert warm_row.alert_candidates == ()

    clock.advance_wall(60.0)
    hot = await _tick_quote(clock, provider, engine, "00700.HK", 101.5, high=101.5)
    hot_row = hot.for_symbol("00700.HK")
    assert hot_row is not None
    assert hot_row.level_after is SchedulerLevel.HOT
    assert hot_row.alert_candidates

    clock.advance_wall(1.0)
    suppressed = await _tick_quote(clock, provider, engine, "00700.HK", 101.5, high=101.5)
    suppressed_row = suppressed.for_symbol("00700.HK")
    assert suppressed_row is not None
    assert suppressed_row.alert_candidates == ()
    assert suppressed_row.level_after is SchedulerLevel.HOT
    assert engine.states.get("00700.HK").level is SchedulerLevel.HOT  # type: ignore[union-attr]
    assert engine.states.get("00700.HK").active_signals  # type: ignore[union-attr]


async def test_scheduler_dwell_blocks_immediate_downgrade(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await _tick_quote(clock, provider, engine, "00700.HK", 100.0)
    clock.advance_wall(60.0)
    hot = await _tick_quote(clock, provider, engine, "00700.HK", 101.5, high=101.5)
    assert hot.for_symbol("00700.HK") is not None
    assert engine.scheduler.get_level("00700.HK") is SchedulerLevel.HOT

    clock.advance_wall(60.0)
    clock.advance_monotonic(1.0)
    quiet = await _tick_quote(clock, provider, engine, "00700.HK", 101.5, high=101.5)
    quiet_row = quiet.for_symbol("00700.HK")
    assert quiet_row is not None
    assert quiet_row.level_before is SchedulerLevel.HOT
    assert quiet_row.level_after is SchedulerLevel.HOT
    assert engine.scheduler.get_level("00700.HK") is SchedulerLevel.HOT

    clock.advance_monotonic(29.0)
    later = await _tick_quote(clock, provider, engine, "00700.HK", 101.5, high=101.5)
    later_row = later.for_symbol("00700.HK")
    assert later_row is not None
    assert later_row.level_after is SchedulerLevel.COLD


async def test_one_symbol_pipeline_failure_does_not_stop_others(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.pipeline = ExplodingPipeline(clock)
    engine.watchlist.add("00700.HK")
    engine.watchlist.add("000001.SZ")
    _quote(provider, clock, "00700.HK", 100.0)
    _quote(provider, clock, "000001.SZ", 100.0)
    caplog.set_level(logging.ERROR)
    result = await engine.tick()
    assert "000001.SZ" in caplog.text
    assert "pipeline" in caplog.text
    hk = result.for_symbol("00700.HK")
    sz = result.for_symbol("000001.SZ")
    assert hk is not None
    assert sz is not None
    assert sz.accepted_events == ()
    assert sz.alert_candidates == ()
    assert engine.states.get("00700.HK") is not None
    assert engine.states.get("00700.HK").latest is not None  # type: ignore[union-attr]
    assert engine.states.get("000001.SZ") is not None
    assert engine.states.get("000001.SZ").latest is not None  # type: ignore[union-attr]
    assert engine.states.get("000001.SZ").features is None  # type: ignore[union-attr]
    clock.advance_wall(60.0)
    _quote(provider, clock, "00700.HK", 100.8, high=100.8)
    _quote(provider, clock, "000001.SZ", 100.8, high=100.8)
    second = await engine.tick()
    hk2 = second.for_symbol("00700.HK")
    assert hk2 is not None
    assert hk2.signal_updates
    assert second.for_symbol("000001.SZ") is not None
    assert engine.states.get("00700.HK").active_signals  # type: ignore[union-attr]
    assert engine.states.get("000001.SZ").active_signals == ()  # type: ignore[union-attr]

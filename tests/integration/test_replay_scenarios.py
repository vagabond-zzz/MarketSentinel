from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import (
    EventDirection,
    EventType,
    FeedStatus,
    SchedulerLevel,
    SignalPriority,
)
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _batches(name: str) -> list[list[dict]]:
    path = FIXTURES / name
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _engine(tmp_path: Path, fixture_name: str, *, symbol: str = "00700.HK"):
    batches = _batches(fixture_name)
    start = float(batches[0][0]["market_timestamp"])
    clock = FakeClock(wall=start, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add(symbol)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=ReplayProvider(FIXTURES / fixture_name, clock),
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(cold_interval_s=0.0, warm_interval_s=0.0, hot_interval_s=0.0),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    return clock, engine, batches


async def _run(
    tmp_path: Path, fixture_name: str, *, symbol: str = "00700.HK"
) -> tuple[MarketEngine, list[EngineTickResult]]:
    clock, engine, batches = _engine(tmp_path, fixture_name, symbol=symbol)
    results: list[EngineTickResult] = []
    for batch in batches:
        clock.set_wall(float(batch[0]["market_timestamp"]))
        results.append(await engine.tick())
    return engine, results


@pytest.mark.integration
async def test_replay_normal_market_stays_cold(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "normal_market.jsonl")
    last = results[-1].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert last is not None and state is not None
    assert last.features is not None
    assert last.features.change_1m == pytest.approx(0.0)
    assert last.features.volume_ratio_5m is not None
    assert last.features.volume_ratio_5m == pytest.approx(1.0, abs=0.05)
    assert last.accepted_events == ()
    assert last.alert_candidates == ()
    assert state.level is SchedulerLevel.COLD
    assert state.active_signals == ()


@pytest.mark.integration
async def test_replay_precursor_warms_without_signal(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "pre_signal_warm.jsonl")
    first = results[0].for_symbol("00700.HK")
    second = results[1].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert first is not None and second is not None and state is not None
    assert first.level_after is SchedulerLevel.COLD
    assert second.accepted_events == ()
    assert second.alert_candidates == ()
    assert second.level_after is SchedulerLevel.WARM
    assert state.level is SchedulerLevel.WARM
    assert state.active_signals == ()


@pytest.mark.integration
async def test_replay_rapid_move_hot_alert_then_cooldown(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "rapid_move.jsonl")
    move = results[1].for_symbol("00700.HK")
    quiet = results[2].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert move is not None and quiet is not None and state is not None
    assert any(item.type is EventType.RAPID_MOVE for item in move.accepted_events)
    assert move.alert_candidates
    assert move.level_after is SchedulerLevel.HOT
    signal_id = move.alert_candidates[0].id
    assert quiet.alert_candidates == ()
    assert any(item.id == signal_id for item in state.active_signals)
    assert state.level is SchedulerLevel.HOT


@pytest.mark.integration
async def test_replay_volume_spike_needs_warmup(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "volume_spike.jsonl")
    early = results[5].for_symbol("00700.HK")
    assert early is not None and early.features is not None
    assert early.features.volume_ratio_5m is None
    assert early.features.volume_ratio_1m is None
    assert all(item.type is not EventType.VOLUME_SPIKE for item in early.accepted_events)

    last = results[-1].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert last is not None and state is not None
    assert any(item.type is EventType.VOLUME_SPIKE for item in last.accepted_events)
    assert last.alert_candidates
    assert last.alert_candidates[0].family == "volume"
    assert last.alert_candidates[0].direction is EventDirection.NONE


@pytest.mark.integration
async def test_replay_price_volume_breakout_episode(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "price_volume_breakout.jsonl")
    event_tick = results[-2].for_symbol("00700.HK")
    follow = results[-1].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert event_tick is not None and follow is not None and state is not None
    types = {item.type for item in event_tick.accepted_events}
    assert EventType.RAPID_MOVE in types
    assert EventType.VOLUME_SPIKE in types
    assert EventType.PRICE_VOLUME_EXPANSION in types
    assert EventType.DAY_HIGH_BREAKOUT in types
    signal = event_tick.alert_candidates[0]
    assert signal.family == "price_volume"
    assert signal.direction is EventDirection.UP
    assert signal.priority is SignalPriority.IMPORTANT
    assert {item.id for item in event_tick.accepted_events} <= set(signal.event_ids)
    assert event_tick.level_after is SchedulerLevel.HOT
    assert follow.alert_candidates == ()
    updated = state.active_signals[0]
    assert updated.id == signal.id
    assert updated.family == "price_volume"
    assert any(item.type is EventType.DAY_HIGH_BREAKOUT for item in follow.accepted_events) or (
        set(signal.event_ids) <= set(updated.event_ids)
    )


@pytest.mark.integration
async def test_replay_episode_expires_then_new_id_gets_first_alert(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "episode_lifecycle.jsonl")
    first = results[1].for_symbol("00700.HK")
    expired = results[2].for_symbol("00700.HK")
    second = results[3].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert first is not None and expired is not None and second is not None and state is not None
    first_id = first.alert_candidates[0].id
    created = first.alert_candidates[0].signal_created_timestamp
    assert expired.alert_candidates == ()
    assert expired.signal_updates == ()
    assert engine.states.get("00700.HK") is not None
    assert all(item.id != first_id for item in expired.signal_updates)
    assert second.alert_candidates
    new_signal = second.alert_candidates[0]
    assert new_signal.id != first_id
    assert new_signal.signal_created_timestamp != created
    assert new_signal.id in {item.id for item in state.active_signals}


@pytest.mark.integration
async def test_replay_reversal_has_independent_down_alert(tmp_path: Path) -> None:
    engine, results = await _run(tmp_path, "reversal.jsonl")
    up = results[1].for_symbol("00700.HK")
    down = results[2].for_symbol("00700.HK")
    assert up is not None and down is not None
    up_id = up.alert_candidates[0].id
    assert up.alert_candidates[0].direction is EventDirection.UP
    assert down.alert_candidates
    down_signal = down.alert_candidates[0]
    assert down_signal.id != up_id
    assert down_signal.direction is EventDirection.DOWN
    live = engine.states.get("00700.HK")
    assert live is not None
    directions = {item.direction for item in live.active_signals}
    assert EventDirection.UP in directions
    assert EventDirection.DOWN in directions
    assert all(
        item.direction is not EventDirection.UP or down_signal.id not in item.event_ids
        for item in live.active_signals
    )


@pytest.mark.integration
async def test_replay_active_signals_keep_untouched_tape_when_vwap_updates(
    tmp_path: Path,
) -> None:
    engine, results = await _run(tmp_path, "tape_then_vwap.jsonl")
    tape = results[1].for_symbol("00700.HK")
    vwap = results[2].for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert tape is not None and vwap is not None and state is not None
    tape_id = next(item.id for item in tape.signal_updates if item.family != "vwap")
    families = {item.family for item in state.active_signals}
    ids = {item.id for item in state.active_signals}
    assert tape_id in ids
    assert "vwap" in families
    assert any(item.family != "vwap" for item in state.active_signals)
    assert any(item.type is EventType.VWAP_CROSS for item in vwap.accepted_events)


@pytest.mark.integration
async def test_replay_alert_candidates_are_edge_triggered(tmp_path: Path) -> None:
    _, results = await _run(tmp_path, "rapid_move.jsonl")
    first = results[1].for_symbol("00700.HK")
    second = results[2].for_symbol("00700.HK")
    assert first is not None and second is not None
    assert first.alert_candidates
    assert second.alert_candidates == ()


@pytest.mark.integration
async def test_disconnected_fetch_does_not_forge_events(tmp_path: Path) -> None:
    clock, engine, batches = _engine(tmp_path, "rapid_move.jsonl")
    for batch in batches[:2]:
        clock.set_wall(float(batch[0]["market_timestamp"]))
        await engine.tick()
    signal_ids = {item.id for item in engine.states.get("00700.HK").active_signals}  # type: ignore[union-attr]
    assert signal_ids
    engine.provider = FakeProvider(clock)
    engine.provider.set_timeout(True)
    clock.advance_monotonic(30.0)
    result = await engine.tick()
    row = result.for_symbol("00700.HK")
    state = engine.states.get("00700.HK")
    assert row is not None and state is not None
    assert row.accepted_events == ()
    assert row.alert_candidates == ()
    assert {item.id for item in state.active_signals} == signal_ids
    assert engine.health.status("00700.HK") is FeedStatus.STALE
    clock.advance_monotonic(30.0)
    await engine.tick()
    await engine.tick()
    assert engine.health.status("00700.HK") is FeedStatus.DISCONNECTED
    assert engine.states.get("00700.HK").active_signals  # type: ignore[union-attr]

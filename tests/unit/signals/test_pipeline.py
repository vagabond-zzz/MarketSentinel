from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventDirection, EventType, SignalPriority
from market_sentinel.signals.pipeline import SignalPipeline
from tests.unit.events.helpers import make_features


def test_pipeline_emits_immediately_and_upgrades_volume_to_price_volume() -> None:
    clock = FakeClock(wall=10.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    volume_only = make_features(
        market_timestamp=1_700_000_010.0,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, volume_only)
    assert any(item.type is EventType.VOLUME_SPIKE for item in first.accepted_events)
    assert len(first.signal_updates) == 1
    signal = first.signal_updates[0]
    assert signal.family == "volume"
    assert signal.priority is SignalPriority.NOTICE
    assert first.alert_candidates == first.signal_updates
    assert len(first.traces) == 1

    later = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    second = pipeline.process(volume_only, later)
    assert any(item.type is EventType.RAPID_MOVE for item in second.accepted_events)
    assert len(second.signal_updates) == 1
    upgraded = second.signal_updates[0]
    assert upgraded.id == signal.id
    assert upgraded.family == "price_volume"
    assert upgraded.priority is SignalPriority.IMPORTANT
    assert second.alert_candidates[0].id == upgraded.id


def test_same_tick_tape_rules_compose_one_final_signal() -> None:
    clock = FakeClock(wall=20.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    types = {item.type for item in result.accepted_events}
    assert EventType.RAPID_MOVE in types
    assert EventType.VOLUME_SPIKE in types
    assert EventType.PRICE_VOLUME_EXPANSION in types
    tape = [item for item in result.signal_updates if item.family == "price_volume"]
    assert len(tape) == 1
    assert len(result.signal_updates) == 1
    event_ids = set(tape[0].event_ids)
    assert {item.id for item in result.accepted_events} <= event_ids
    assert result.signal_updates == pipeline.composer.active_signals(current.symbol)
    assert tape[0].priority is SignalPriority.IMPORTANT


def test_same_tick_preserves_tape_and_vwap_lineages() -> None:
    clock = FakeClock(wall=30.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(
        market_timestamp=1_700_000_000.0,
        above_vwap=False,
        vwap=100.0,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        above_vwap=True,
        vwap=100.0,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    families = {item.family for item in result.signal_updates}
    assert "price_volume" in families
    assert "vwap" in families
    assert len(result.signal_updates) == 2
    assert len(result.traces) == 2
    assert {item.family for item in result.alert_candidates} == families


def test_cooldown_suppresses_alert_but_still_updates_signal_state() -> None:
    clock = FakeClock(wall=40.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    seeded = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, seeded)
    assert first.alert_candidates[0].priority is SignalPriority.IMPORTANT
    signal_id = first.alert_candidates[0].id

    with_breakout = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.1,
    )
    second = pipeline.process(seeded, with_breakout)
    assert any(item.type is EventType.DAY_HIGH_BREAKOUT for item in second.accepted_events)
    assert second.alert_candidates == ()
    assert len(second.signal_updates) == 1
    updated = second.signal_updates[0]
    assert updated.id == signal_id
    assert updated.family == "price_volume"
    assert updated.priority is SignalPriority.IMPORTANT
    assert any(
        item.type is EventType.DAY_HIGH_BREAKOUT
        for item in second.accepted_events
        if item.id in updated.event_ids
    )
    assert second.traces[0].event_ids == updated.event_ids
    assert "day_high_breakout" in " ".join(second.traces[0].rule_names)


def test_new_episode_after_expiry_has_independent_first_alert() -> None:
    clock = FakeClock(wall=50.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    first_features = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, first_features)
    assert len(first.alert_candidates) == 1
    first_id = first.alert_candidates[0].id

    later = make_features(
        market_timestamp=1_700_000_200.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    second = pipeline.process(first_features, later)
    assert len(second.alert_candidates) == 1
    assert second.alert_candidates[0].id != first_id
    assert second.alert_candidates[0].family == first.alert_candidates[0].family
    assert second.alert_candidates[0].priority is first.alert_candidates[0].priority


def test_reversal_episode_has_independent_first_alert() -> None:
    clock = FakeClock(wall=60.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    up_features = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    up = pipeline.process(previous, up_features)
    down_features = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=-0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    down = pipeline.process(up_features, down_features)
    assert up.alert_candidates[0].direction is EventDirection.UP
    assert len(down.alert_candidates) == 1
    assert down.alert_candidates[0].id != up.alert_candidates[0].id
    assert down.alert_candidates[0].direction is EventDirection.DOWN


def test_quiet_tick_keeps_active_signal_but_clears_alert_candidates() -> None:
    clock = FakeClock(wall=70.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    active = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, active)
    assert first.alert_candidates
    signal_id = first.alert_candidates[0].id

    quiet = make_features(
        market_timestamp=1_700_000_020.0,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    second = pipeline.process(active, quiet)
    assert second.accepted_events == ()
    assert len(second.signal_updates) == 1
    assert second.signal_updates[0].id == signal_id
    assert second.alert_candidates == ()


def test_expired_episode_is_dropped_from_active_signals() -> None:
    clock = FakeClock(wall=80.0, monotonic=0.0)
    pipeline = SignalPipeline(clock)
    previous = make_features(market_timestamp=1_700_000_000.0)
    active = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, active)
    assert first.signal_updates
    expired = make_features(
        market_timestamp=1_700_000_110.0,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    later = pipeline.process(active, expired)
    assert later.accepted_events == ()
    assert later.signal_updates == ()
    assert later.alert_candidates == ()

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.signals.composer import SignalComposer
from tests.unit.events.helpers import make_features
from tests.unit.signals.helpers import make_event


def test_lookback_continuity_reuses_signal_id_and_created_at() -> None:
    clock = FakeClock(wall=1_000.0)
    composer = SignalComposer(clock)
    volume = make_event(
        event_type=EventType.VOLUME_SPIKE,
        direction=EventDirection.NONE,
        severity=2,
        market_timestamp=100.0,
        ttl_s=120.0,
    )
    first, _ = composer.consume(volume, make_features(volume_ratio_5m=1.8, market_timestamp=100.0))
    clock.advance_wall(10.0)
    move = make_event(
        event_type=EventType.RAPID_MOVE,
        direction=EventDirection.UP,
        severity=2,
        market_timestamp=110.0,
    )
    second, _ = composer.consume(
        move, make_features(change_1m=0.006, volume_ratio_5m=1.8, market_timestamp=110.0)
    )
    assert second.id == first.id
    assert second.signal_created_timestamp == first.signal_created_timestamp == 1_000.0
    assert second.family == "price_volume"
    assert second.direction is EventDirection.UP


def test_expired_episode_gets_new_id_and_created_timestamp() -> None:
    clock = FakeClock(wall=1_000.0)
    composer = SignalComposer(clock)
    volume = make_event(
        event_type=EventType.VOLUME_SPIKE,
        direction=EventDirection.NONE,
        market_timestamp=100.0,
        ttl_s=120.0,
    )
    first, _ = composer.consume(volume, make_features(volume_ratio_5m=1.8))
    clock.advance_wall(10.0)
    move = make_event(
        event_type=EventType.RAPID_MOVE,
        direction=EventDirection.UP,
        market_timestamp=110.0,
    )
    second, _ = composer.consume(move, make_features(change_1m=0.006, volume_ratio_5m=1.8))
    assert second.id == first.id

    clock.advance_wall(50.0)
    later = make_event(
        event_type=EventType.RAPID_MOVE,
        direction=EventDirection.UP,
        market_timestamp=300.0,
    )
    third, _ = composer.consume(later, make_features(change_1m=0.006))
    assert third.id != first.id
    assert third.signal_created_timestamp == 1_060.0
    assert third.signal_created_timestamp != first.signal_created_timestamp
    assert first.id not in {item.id for item in composer.active_signals("00700.HK")}


def test_active_state_is_bounded_to_live_episodes() -> None:
    clock = FakeClock(wall=1.0)
    composer = SignalComposer(clock, lookback_s=90.0)
    for index in range(20):
        ts = 100.0 + index * 100.0
        clock.advance_wall(1.0)
        event = make_event(
            event_type=EventType.RAPID_MOVE,
            direction=EventDirection.UP,
            market_timestamp=ts,
        )
        composer.consume(event, make_features(change_1m=0.006, market_timestamp=ts))
    live = composer.active_signals("00700.HK")
    assert len(live) == 1
    assert all(signal.market_timestamp >= ts - 90.0 for signal in live)

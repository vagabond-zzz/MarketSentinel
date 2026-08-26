from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventType, GeneratedBy, SignalPriority
from market_sentinel.signals.cluster import CLUSTER_LOOKBACK_S, classify_family, events_in_lookback
from market_sentinel.signals.composer import SignalComposer
from tests.unit.events.helpers import make_features
from tests.unit.signals.helpers import make_event


def test_lookback_is_not_a_wait_and_clusters_within_90s() -> None:
    clock = FakeClock(wall=1_000.0)
    composer = SignalComposer(clock)
    volume = make_event(
        event_type=EventType.VOLUME_SPIKE,
        severity=2,
        market_timestamp=100.0,
        ttl_s=120.0,
    )
    features = make_features(volume_ratio_5m=1.8, market_timestamp=100.0)
    first, _trace = composer.consume(volume, features)
    assert first.family == "volume"
    assert first.priority is SignalPriority.NOTICE
    assert first.generated_by is GeneratedBy.RULE
    assert first.signal_created_timestamp == 1_000.0

    clock.advance_wall(10.0)
    move = make_event(
        event_type=EventType.RAPID_MOVE,
        severity=2,
        market_timestamp=110.0,
    )
    second, _ = composer.consume(
        move, make_features(change_1m=0.006, volume_ratio_5m=1.8, market_timestamp=110.0)
    )
    assert second.id == first.id
    assert second.family == "price_volume"
    assert second.priority is SignalPriority.IMPORTANT
    assert second.signal_created_timestamp == first.signal_created_timestamp
    assert volume.id in second.event_ids
    assert move.id in second.event_ids


def test_events_older_than_lookback_are_not_clustered() -> None:
    composer = SignalComposer(FakeClock())
    volume = make_event(event_type=EventType.VOLUME_SPIKE, market_timestamp=100.0, ttl_s=120.0)
    composer.consume(volume, make_features(volume_ratio_5m=1.8))
    later = make_event(
        event_type=EventType.RAPID_MOVE,
        market_timestamp=100.0 + CLUSTER_LOOKBACK_S + 1.0,
    )
    signal, _ = composer.consume(later, make_features(change_1m=0.006))
    assert signal.family == "move"
    assert volume.id not in signal.event_ids


def test_breakout_upgrades_active_price_volume_signal() -> None:
    composer = SignalComposer(FakeClock())
    volume = make_event(event_type=EventType.VOLUME_SPIKE, market_timestamp=10.0, ttl_s=120.0)
    move = make_event(event_type=EventType.RAPID_MOVE, market_timestamp=20.0)
    breakout = make_event(event_type=EventType.DAY_HIGH_BREAKOUT, market_timestamp=30.0, severity=3)
    first, _ = composer.consume(volume, make_features(volume_ratio_5m=1.8))
    composer.consume(move, make_features(change_1m=0.006, volume_ratio_5m=1.8))
    upgraded, trace = composer.consume(
        breakout,
        make_features(
            change_1m=0.006,
            volume_ratio_5m=1.8,
            session_high_ref=100.0,
            session_high_obs=100.1,
        ),
    )
    assert upgraded.id == first.id
    assert upgraded.family == "price_volume"
    assert breakout.id in upgraded.event_ids
    assert trace.family == "price_volume"
    assert "notified" not in upgraded.__dataclass_fields__
    assert "notified" not in trace.__dataclass_fields__


def test_lookback_helper_includes_boundary() -> None:
    early = make_event(market_timestamp=10.0)
    late = make_event(market_timestamp=100.0)
    found = events_in_lookback([early, late], now_market_ts=100.0, lookback_s=90.0)
    assert early in found
    assert late in found
    missed = events_in_lookback([early, late], now_market_ts=100.1, lookback_s=90.0)
    assert early not in missed


def test_classify_family_price_volume() -> None:
    volume = make_event(event_type=EventType.VOLUME_SPIKE)
    move = make_event(event_type=EventType.RAPID_MOVE)
    assert classify_family([volume]) == "volume"
    assert classify_family([volume, move]) == "price_volume"
    assert classify_family([make_event(event_type=EventType.DAY_HIGH_BREAKOUT)]) == "breakout"
    assert classify_family([make_event(event_type=EventType.DAY_LOW_BREAKDOWN)]) == "breakdown"
    assert classify_family([]) == "other"


def test_vwap_and_other_symbols_do_not_join_tape_cluster() -> None:
    composer = SignalComposer(FakeClock())
    volume = make_event(event_type=EventType.VOLUME_SPIKE, market_timestamp=10.0, ttl_s=120.0)
    vwap = make_event(event_type=EventType.VWAP_CROSS, market_timestamp=11.0)
    other = make_event(symbol="600519.SH", event_type=EventType.RAPID_MOVE, market_timestamp=12.0)
    tape, _ = composer.consume(volume, make_features(volume_ratio_5m=1.8))
    cross, _ = composer.consume(vwap, make_features(above_vwap=True, vwap=100.0))
    other_sig, _ = composer.consume(other, make_features(symbol="600519.SH", change_1m=0.006))
    assert tape.id != cross.id
    assert tape.family == "volume"
    assert cross.family == "vwap"
    assert other_sig.symbol == "600519.SH"
    assert other_sig.id != tape.id

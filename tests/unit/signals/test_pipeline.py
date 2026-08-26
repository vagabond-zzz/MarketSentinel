from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventType, SignalPriority
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
    accepted, signal, trace = pipeline.process(previous, volume_only)
    assert any(item.type is EventType.VOLUME_SPIKE for item in accepted)
    assert signal is not None
    assert trace is not None
    assert signal.family == "volume"
    assert signal.priority is SignalPriority.NOTICE

    later = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    accepted2, upgraded, _ = pipeline.process(volume_only, later)
    assert any(item.type is EventType.RAPID_MOVE for item in accepted2)
    assert upgraded is not None
    assert upgraded.id == signal.id
    assert upgraded.family == "price_volume"
    assert upgraded.priority is SignalPriority.IMPORTANT

    with_breakout = make_features(
        market_timestamp=1_700_000_030.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.1,
    )
    accepted3, emitted3, _ = pipeline.process(later, with_breakout)
    assert any(item.type is EventType.DAY_HIGH_BREAKOUT for item in accepted3)
    # Composer upgrades immediately; same-family same-priority cooldown may suppress re-emit.
    if emitted3 is not None:
        assert emitted3.id == signal.id
        assert emitted3.family == "price_volume"

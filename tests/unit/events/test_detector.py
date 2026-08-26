from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventType
from market_sentinel.events.detector import EventDetector
from market_sentinel.events.rules import default_rules
from market_sentinel.events.thresholds import RAPID_1M_SEV2
from tests.unit.events.helpers import make_features


def test_default_rules_are_the_six_frozen_v02_rules() -> None:
    names = [rule.name for rule in default_rules()]
    assert names == [
        "rapid_move",
        "volume_spike",
        "price_volume_expansion",
        "day_high_breakout",
        "day_low_breakdown",
        "vwap_cross",
    ]
    assert "momentum" not in names
    assert "volatility_expansion" not in names


def test_detector_emits_independent_events_from_each_rule() -> None:
    clock = FakeClock(wall=1_700_000_200.0)
    previous = make_features(above_vwap=False, vwap=100.0, session_high_ref=100.0)
    current = make_features(
        change_1m=RAPID_1M_SEV2,
        volume_ratio_5m=1.8,
        above_vwap=True,
        vwap=100.0,
        session_high_ref=100.0,
        session_high_obs=100.1,
        change_5m=0.001,
    )
    events = EventDetector(clock).evaluate(previous, current)
    types = {event.type for event in events}
    assert EventType.RAPID_MOVE in types
    assert EventType.VOLUME_SPIKE in types
    assert EventType.PRICE_VOLUME_EXPANSION in types
    assert EventType.DAY_HIGH_BREAKOUT in types
    assert EventType.VWAP_CROSS in types
    assert all(event.detected_timestamp == 1_700_000_200.0 for event in events)

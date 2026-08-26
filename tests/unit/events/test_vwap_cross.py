from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.events.rules.vwap_cross import VwapCrossRule
from tests.unit.events.helpers import DETECTED_AT, make_features

RULE = VwapCrossRule()


def test_vwap_cross_below_flip_and_with_move() -> None:
    previous = make_features(above_vwap=False, vwap=100.0)
    mild = make_features(above_vwap=True, vwap=100.0, change_5m=0.007)
    strong = make_features(above_vwap=True, vwap=100.0, change_5m=0.008)
    up = RULE.evaluate(previous, mild, detected_at=DETECTED_AT)[0]
    assert up.type is EventType.VWAP_CROSS
    assert up.direction is EventDirection.UP
    assert up.severity == 2
    assert up.ttl_s == 60.0
    assert RULE.evaluate(previous, strong, detected_at=DETECTED_AT)[0].severity == 3


def test_vwap_cross_down_and_no_cross() -> None:
    previous = make_features(above_vwap=True, vwap=100.0)
    current = make_features(above_vwap=False, vwap=100.0)
    down = RULE.evaluate(previous, current, detected_at=DETECTED_AT)[0]
    assert down.direction is EventDirection.DOWN
    same = make_features(above_vwap=True, vwap=100.0)
    assert RULE.evaluate(previous, same, detected_at=DETECTED_AT) == []


def test_vwap_cross_none_features_do_not_fire() -> None:
    previous = make_features(above_vwap=False, vwap=100.0)
    assert (
        RULE.evaluate(None, make_features(above_vwap=True, vwap=100.0), detected_at=DETECTED_AT)
        == []
    )
    assert (
        RULE.evaluate(previous, make_features(above_vwap=True, vwap=None), detected_at=DETECTED_AT)
        == []
    )
    assert (
        RULE.evaluate(
            make_features(above_vwap=None, vwap=100.0),
            make_features(above_vwap=True, vwap=100.0),
            detected_at=DETECTED_AT,
        )
        == []
    )
    assert (
        RULE.evaluate(
            previous,
            make_features(above_vwap=None, vwap=100.0),
            detected_at=DETECTED_AT,
        )
        == []
    )

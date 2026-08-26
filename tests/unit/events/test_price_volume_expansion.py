import pytest

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.events.rules.price_volume_expansion import PriceVolumeExpansionRule
from tests.unit.events.helpers import DETECTED_AT, make_features

RULE = PriceVolumeExpansionRule()


def _eval(**overrides: object):
    return RULE.evaluate(None, make_features(**overrides), detected_at=DETECTED_AT)


@pytest.mark.parametrize(
    ("change_1m", "ratio_5m", "severity"),
    [
        (0.00599, 1.8, None),
        (0.006, 1.79, None),
        (0.006, 1.8, 3),
        (0.015, 1.8, 5),
        (0.006, 6.0, 5),
        (0.010, 2.5, 4),
    ],
)
def test_price_volume_expansion_thresholds(
    change_1m: float,
    ratio_5m: float,
    severity: int | None,
) -> None:
    events = _eval(change_1m=change_1m, volume_ratio_5m=ratio_5m)
    if severity is None:
        assert events == []
        return
    event = events[0]
    assert event.type is EventType.PRICE_VOLUME_EXPANSION
    assert event.severity == severity
    assert event.ttl_s == 120.0


def test_price_volume_expansion_direction_follows_move() -> None:
    up = _eval(change_1m=0.006, volume_ratio_5m=1.8)[0]
    down = _eval(change_1m=-0.006, volume_ratio_5m=1.8)[0]
    assert up.direction is EventDirection.UP
    assert down.direction is EventDirection.DOWN


def test_price_volume_expansion_none_features_do_not_fire() -> None:
    assert _eval(change_1m=0.006) == []
    assert _eval(volume_ratio_5m=1.8) == []
    assert _eval() == []

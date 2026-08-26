import pytest

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.events.rules.rapid_move import RapidMoveRule
from market_sentinel.events.thresholds import RAPID_1M_SEV2, RAPID_1M_SEV3, RAPID_1M_SEV4
from tests.unit.events.helpers import DETECTED_AT, make_features

RULE = RapidMoveRule()


def _eval(**overrides: object):
    return RULE.evaluate(None, make_features(**overrides), detected_at=DETECTED_AT)


@pytest.mark.parametrize(
    ("change_1m", "change_5m", "severity"),
    [
        (0.00599, None, None),
        (RAPID_1M_SEV2, None, 2),
        (0.0061, None, 2),
        (RAPID_1M_SEV3, None, 3),
        (None, 0.0119, None),
        (None, 0.012, 3),
        (RAPID_1M_SEV4, None, 4),
        (None, 0.020, 4),
        (None, 0.035, 5),
        (0.006, 0.035, 5),
        (None, None, None),
    ],
)
def test_rapid_move_thresholds(
    change_1m: float | None,
    change_5m: float | None,
    severity: int | None,
) -> None:
    events = _eval(change_1m=change_1m, change_5m=change_5m)
    if severity is None:
        assert events == []
        return
    assert len(events) == 1
    event = events[0]
    assert event.type is EventType.RAPID_MOVE
    assert event.severity == severity
    assert event.rule_name == "rapid_move"
    assert event.ttl_s == 60.0
    assert event.dedupe_key.endswith("|rapid_move|up") or event.dedupe_key.endswith(
        "|rapid_move|down"
    )


def test_rapid_move_direction_follows_signed_window() -> None:
    up = _eval(change_1m=0.006)[0]
    down = _eval(change_1m=-0.006)[0]
    assert up.direction is EventDirection.UP
    assert down.direction is EventDirection.DOWN
    five_down = _eval(change_1m=0.001, change_5m=-0.035)[0]
    assert five_down.severity == 5
    assert five_down.direction is EventDirection.DOWN


def test_rapid_move_none_features_do_not_fire() -> None:
    assert _eval() == []


def test_rapid_move_does_not_treat_point_six_as_point_six_percent() -> None:
    assert RAPID_1M_SEV2 == 0.006
    assert _eval(change_1m=0.0006) == []
    assert _eval(change_1m=0.006)[0].severity == 2

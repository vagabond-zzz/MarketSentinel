import pytest

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.events.rules.day_high_breakout import DayHighBreakoutRule
from tests.unit.events.helpers import DETECTED_AT, make_features

RULE = DayHighBreakoutRule()


def _eval(**overrides: object):
    return RULE.evaluate(None, make_features(**overrides), detected_at=DETECTED_AT)


@pytest.mark.parametrize(
    ("obs", "severity"),
    [
        (1000.0, None),
        (1001.0, 3),
        (1003.0, 4),
        (1004.0, 4),
        (1008.0, 5),
    ],
)
def test_day_high_breakout_thresholds(obs: float, severity: int | None) -> None:
    events = _eval(session_high_ref=1000.0, session_high_obs=obs)
    if severity is None:
        assert events == []
        return
    event = events[0]
    assert event.type is EventType.DAY_HIGH_BREAKOUT
    assert event.direction is EventDirection.UP
    assert event.severity == severity
    assert event.ttl_s == 60.0


def test_day_high_breakout_uses_provider_obs_not_price_only() -> None:
    # obs = max(price, snapshot.high); price may have retraced below the ref.
    events = _eval(session_high_ref=104.0, session_high_obs=104.1)
    assert events[0].severity == 3
    assert events[0].metrics["session_high_obs"] == 104.1


def test_day_high_breakout_first_tick_without_ref_is_silent() -> None:
    assert _eval(session_high_ref=None, session_high_obs=110.0) == []


def test_day_high_breakout_none_ref_does_not_compare_price_alone() -> None:
    assert _eval(session_high_ref=None, session_high_obs=100.0) == []

import pytest

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.events.rules.day_low_breakdown import DayLowBreakdownRule
from tests.unit.events.helpers import DETECTED_AT, make_features

RULE = DayLowBreakdownRule()


def _eval(**overrides: object):
    return RULE.evaluate(None, make_features(**overrides), detected_at=DETECTED_AT)


@pytest.mark.parametrize(
    ("obs", "severity"),
    [
        (1000.0, None),
        (999.0, 3),
        (997.0, 4),
        (992.0, 5),
    ],
)
def test_day_low_breakdown_thresholds(obs: float, severity: int | None) -> None:
    events = _eval(session_low_ref=1000.0, session_low_obs=obs)
    if severity is None:
        assert events == []
        return
    event = events[0]
    assert event.type is EventType.DAY_LOW_BREAKDOWN
    assert event.direction is EventDirection.DOWN
    assert event.severity == severity
    assert event.ttl_s == 60.0


def test_day_low_breakdown_uses_provider_obs_not_price_only() -> None:
    events = _eval(session_low_ref=96.0, session_low_obs=95.9)
    assert events[0].severity == 3
    assert events[0].metrics["session_low_obs"] == 95.9


def test_day_low_breakdown_first_tick_without_ref_is_silent() -> None:
    assert _eval(session_low_ref=None, session_low_obs=90.0) == []

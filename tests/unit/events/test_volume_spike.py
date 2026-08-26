import pytest

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.events.rules.volume_spike import VolumeSpikeRule
from tests.unit.events.helpers import DETECTED_AT, make_features

RULE = VolumeSpikeRule()


def _eval(**overrides: object):
    return RULE.evaluate(None, make_features(**overrides), detected_at=DETECTED_AT)


@pytest.mark.parametrize(
    ("ratio_1m", "ratio_5m", "severity"),
    [
        (None, 1.79, None),
        (None, 1.8, 2),
        (None, 1.81, 2),
        (None, 2.5, 3),
        (3.0, 1.0, 3),
        (2.9, 1.0, None),
        (None, 4.0, 4),
        (None, 6.0, 5),
        (None, None, None),
    ],
)
def test_volume_spike_thresholds(
    ratio_1m: float | None,
    ratio_5m: float | None,
    severity: int | None,
) -> None:
    events = _eval(volume_ratio_1m=ratio_1m, volume_ratio_5m=ratio_5m)
    if severity is None:
        assert events == []
        return
    assert len(events) == 1
    event = events[0]
    assert event.type is EventType.VOLUME_SPIKE
    assert event.direction is EventDirection.NONE
    assert event.severity == severity
    assert event.ttl_s == 120.0
    assert event.dedupe_key == "00700.HK|volume_spike|none"


def test_volume_spike_none_features_do_not_fire() -> None:
    assert _eval() == []

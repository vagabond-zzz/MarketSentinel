from market_sentinel.domain.enums import EventType, SchedulerLevel
from market_sentinel.orchestration.warming import WarmingPolicy
from tests.unit.events.helpers import make_features
from tests.unit.signals.helpers import make_event


def test_warming_maps_quiet_precursor_and_strong_conditions() -> None:
    policy = WarmingPolicy()
    quiet = make_features()
    assert policy.request("00700.HK", quiet, ()).level is SchedulerLevel.COLD

    precursor = make_features(change_1m=0.004)
    assert policy.request("00700.HK", precursor, ()).level is SchedulerLevel.WARM

    strong = make_features(change_5m=0.012)
    assert policy.request("00700.HK", strong, ()).level is SchedulerLevel.HOT

    breakout = make_event(event_type=EventType.DAY_HIGH_BREAKOUT, severity=3)
    assert policy.request("00700.HK", quiet, (breakout,)).level is SchedulerLevel.HOT

    beyond = make_features(session_high_ref=100.0, session_high_obs=100.4)
    assert policy.request("00700.HK", beyond, ()).level is SchedulerLevel.HOT


def test_warming_ignores_alert_cooldown() -> None:
    policy = WarmingPolicy()
    features = make_features(change_5m=0.015)
    request = policy.request("00700.HK", features, ())
    assert request.level is SchedulerLevel.HOT
    assert request.reason == "strong"

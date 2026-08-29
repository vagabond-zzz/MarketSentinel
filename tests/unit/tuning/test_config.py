from __future__ import annotations

import math
from dataclasses import replace

import pytest
from tests.unit.events.helpers import make_features

from market_sentinel.errors import TuningConfigError
from market_sentinel.orchestration.warming import HOT_CHANGE_5M, WarmingConfig, WarmingPolicy
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.signals.cluster import CLUSTER_LOOKBACK_S
from market_sentinel.signals.cooldown import DEFAULT_COOLDOWN_S, CooldownGate
from market_sentinel.tuning.config import (
    DEFERRED_TUNING_PARAMETER_NAMES,
    OFFLINE_TUNING_CONFIG_ALLOWLIST,
    OfflineTuningConfig,
    capture_baseline_config,
    tuning_parameter_inventory,
)

_INERT_INTEL = (
    "router_min_priority",
    "router_require_alert_edge",
    "router_min_convergence_types",
    "episode_max_calls",
    "allow_escalation_recall",
)
_FROZEN_TIME = (
    "cooldown_s",
    "upgrade_dwell_s",
    "hot_downgrade_dwell_s",
    "warm_downgrade_dwell_s",
)


def test_baseline_capture_equals_production_defaults() -> None:
    baseline = capture_baseline_config()
    warming = WarmingConfig()
    assert baseline.cluster_lookback_s == CLUSTER_LOOKBACK_S
    assert baseline.hot_event_severity == warming.hot_event_severity
    assert baseline.hot_volume_ratio_5m == warming.hot_volume_ratio_5m
    assert baseline.hot_change_5m == warming.hot_change_5m
    assert baseline.warm_change_1m == warming.warm_change_1m
    assert baseline.warm_change_5m == warming.warm_change_5m
    assert baseline.warm_volume_ratio == warming.warm_volume_ratio
    assert not hasattr(baseline, "cooldown_s")
    assert not hasattr(baseline, "router_min_priority")
    assert not hasattr(baseline, "episode_max_calls")
    assert CooldownGate.__init__.__defaults__[0] == DEFAULT_COOLDOWN_S
    scheduler = SchedulerPolicy()
    assert scheduler.upgrade_dwell_s == 0.0
    assert scheduler.hot_downgrade_dwell_s == 30.0


def test_supported_parameters_are_strict_allowlist() -> None:
    supported = {item.name for item in tuning_parameter_inventory() if item.status == "supported"}
    deferred = {item.name for item in tuning_parameter_inventory() if item.status == "deferred"}
    assert supported == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)
    assert deferred == set(DEFERRED_TUNING_PARAMETER_NAMES)
    assert supported.isdisjoint(DEFERRED_TUNING_PARAMETER_NAMES)
    record = capture_baseline_config().to_record()
    assert set(record) == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)


def test_intelligence_and_monotonic_fields_are_deferred() -> None:
    by_name = {item.name: item for item in tuning_parameter_inventory()}
    for name in _INERT_INTEL:
        assert by_name[name].status == "deferred"
        assert "does not attach Intelligence" in by_name[name].reason
        assert name not in OFFLINE_TUNING_CONFIG_ALLOWLIST
    for name in _FROZEN_TIME:
        assert by_name[name].status == "deferred"
        assert "freezes monotonic time" in by_name[name].reason
        assert name not in OFFLINE_TUNING_CONFIG_ALLOWLIST


def test_unknown_parameter_rejected_from_record() -> None:
    payload = capture_baseline_config().to_record()
    payload["notes"] = "nope"
    with pytest.raises(TuningConfigError, match="unknown"):
        OfflineTuningConfig.from_record(payload)


def test_nan_and_inf_rejected() -> None:
    payload = capture_baseline_config().to_record()
    payload["cluster_lookback_s"] = math.nan
    with pytest.raises(TuningConfigError, match="finite"):
        OfflineTuningConfig.from_record(payload)
    payload = capture_baseline_config().to_record()
    payload["cluster_lookback_s"] = math.inf
    with pytest.raises(TuningConfigError, match="finite"):
        OfflineTuningConfig.from_record(payload)


def test_invalid_hot_event_severity_rejected() -> None:
    payload = capture_baseline_config().to_record()
    payload["hot_event_severity"] = 9
    with pytest.raises(TuningConfigError, match="hot_event_severity"):
        OfflineTuningConfig.from_record(payload)


@pytest.mark.parametrize(
    "field,value",
    [
        ("cooldown_s", 1.0),
        ("upgrade_dwell_s", 1.0),
        ("hot_downgrade_dwell_s", 1.0),
        ("warm_downgrade_dwell_s", 1.0),
        ("router_min_priority", "IMPORTANT"),
        ("router_require_alert_edge", False),
        ("router_min_convergence_types", 3),
        ("episode_max_calls", 2),
        ("allow_escalation_recall", False),
        ("cold_interval_s", 10.0),
    ],
)
def test_deferred_parameter_cannot_enter_candidate(field: str, value: object) -> None:
    payload = capture_baseline_config().to_record()
    payload[field] = value
    with pytest.raises(TuningConfigError, match="deferred"):
        OfflineTuningConfig.from_record(payload)
    assert field in DEFERRED_TUNING_PARAMETER_NAMES
    assert field not in OFFLINE_TUNING_CONFIG_ALLOWLIST


def test_warming_default_constructor_unchanged() -> None:
    policy = WarmingPolicy()
    strong = make_features(change_5m=HOT_CHANGE_5M)
    assert policy.request("00700.HK", strong, ()).level.value == "HOT"
    quiet = make_features(change_5m=0.001)
    custom = WarmingPolicy(
        WarmingConfig(hot_change_5m=0.99, warm_change_5m=0.98, warm_change_1m=0.97)
    )
    assert custom.request("00700.HK", strong, ()).level.value == "COLD"
    assert WarmingPolicy().request("00700.HK", quiet, ()).level.value == "COLD"


def test_baseline_round_trip() -> None:
    original = capture_baseline_config()
    restored = OfflineTuningConfig.from_record(original.to_record())
    assert restored == original


def test_replace_candidate_keeps_other_production_defaults() -> None:
    candidate = replace(capture_baseline_config(), cluster_lookback_s=1.0)
    assert candidate.cluster_lookback_s == 1.0
    assert candidate.warm_change_1m == WarmingConfig().warm_change_1m

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from tests.unit.events.helpers import make_features

from market_sentinel.domain.enums import SignalPriority
from market_sentinel.errors import TuningConfigError
from market_sentinel.intelligence.contract import EpisodeCallBudget
from market_sentinel.intelligence.router import RouterPolicy
from market_sentinel.orchestration.warming import HOT_CHANGE_5M, WarmingConfig, WarmingPolicy
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.signals.cluster import CLUSTER_LOOKBACK_S
from market_sentinel.signals.cooldown import DEFAULT_COOLDOWN_S, CooldownGate
from market_sentinel.tuning.config import (
    DEFERRED_TUNING_PARAMETER_NAMES,
    OFFLINE_TUNING_CONFIG_ALLOWLIST,
    capture_baseline_config,
    tuning_parameter_inventory,
)


def test_baseline_capture_equals_production_defaults() -> None:
    baseline = capture_baseline_config()
    scheduler = SchedulerPolicy()
    router = RouterPolicy()
    budget = EpisodeCallBudget()
    warming = WarmingConfig()
    assert baseline.cooldown_s == DEFAULT_COOLDOWN_S
    assert CooldownGate.__init__.__defaults__[0] == DEFAULT_COOLDOWN_S
    assert baseline.cluster_lookback_s == CLUSTER_LOOKBACK_S
    assert baseline.upgrade_dwell_s == scheduler.upgrade_dwell_s
    assert baseline.hot_downgrade_dwell_s == scheduler.hot_downgrade_dwell_s
    assert baseline.warm_downgrade_dwell_s == scheduler.warm_downgrade_dwell_s
    assert baseline.hot_event_severity == warming.hot_event_severity
    assert baseline.hot_volume_ratio_5m == warming.hot_volume_ratio_5m
    assert baseline.hot_change_5m == warming.hot_change_5m
    assert baseline.warm_change_1m == warming.warm_change_1m
    assert baseline.warm_change_5m == warming.warm_change_5m
    assert baseline.warm_volume_ratio == warming.warm_volume_ratio
    assert baseline.router_min_priority is router.min_priority
    assert baseline.router_require_alert_edge is router.require_alert_edge
    assert baseline.router_min_convergence_types == router.min_convergence_types
    assert baseline.episode_max_calls == budget.max_calls
    assert baseline.allow_escalation_recall is budget.allow_escalation_recall


def test_supported_parameters_are_strict_allowlist() -> None:
    supported = {item.name for item in tuning_parameter_inventory() if item.status == "supported"}
    assert supported == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)
    record = capture_baseline_config().to_record()
    assert set(record) == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)


def test_unknown_parameter_rejected_from_record() -> None:
    payload = capture_baseline_config().to_record()
    payload["notes"] = "nope"
    with pytest.raises(TuningConfigError, match="unknown"):
        from market_sentinel.tuning.config import OfflineTuningConfig

        OfflineTuningConfig.from_record(payload)


def test_nan_and_inf_rejected() -> None:
    payload = capture_baseline_config().to_record()
    payload["cooldown_s"] = math.nan
    from market_sentinel.tuning.config import OfflineTuningConfig

    with pytest.raises(TuningConfigError, match="finite"):
        OfflineTuningConfig.from_record(payload)
    payload = capture_baseline_config().to_record()
    payload["cluster_lookback_s"] = math.inf
    with pytest.raises(TuningConfigError, match="finite"):
        OfflineTuningConfig.from_record(payload)


def test_invalid_enum_rejected() -> None:
    payload = capture_baseline_config().to_record()
    payload["router_min_priority"] = "urgent"
    from market_sentinel.tuning.config import OfflineTuningConfig

    with pytest.raises(TuningConfigError, match="router_min_priority"):
        OfflineTuningConfig.from_record(payload)


def test_deferred_parameter_cannot_enter_candidate() -> None:
    payload = capture_baseline_config().to_record()
    payload["cold_interval_s"] = 10.0
    from market_sentinel.tuning.config import OfflineTuningConfig

    with pytest.raises(TuningConfigError, match="deferred"):
        OfflineTuningConfig.from_record(payload)
    assert "cold_interval_s" in DEFERRED_TUNING_PARAMETER_NAMES
    assert "cold_interval_s" not in OFFLINE_TUNING_CONFIG_ALLOWLIST


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
    from market_sentinel.tuning.config import OfflineTuningConfig

    original = capture_baseline_config()
    restored = OfflineTuningConfig.from_record(original.to_record())
    assert restored == original
    assert restored.router_min_priority is SignalPriority.IMPORTANT


def test_replace_candidate_keeps_other_production_defaults() -> None:
    candidate = replace(capture_baseline_config(), cooldown_s=60.0)
    assert candidate.cooldown_s == 60.0
    assert candidate.cluster_lookback_s == CLUSTER_LOOKBACK_S

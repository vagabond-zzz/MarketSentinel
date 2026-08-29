from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from market_sentinel.errors import TuningConfigError
from market_sentinel.events.thresholds import (
    BREAKOUT_SEV4,
    BREAKOUT_SEV5,
    RAPID_1M_SEV2,
    RAPID_1M_SEV3,
    RAPID_1M_SEV4,
    RAPID_5M_SEV3,
    RAPID_5M_SEV4,
    RAPID_5M_SEV5,
    TTL_LONG_S,
    TTL_SHORT_S,
    VOL_1M_SEV3,
    VOL_5M_SEV2,
    VOL_5M_SEV3,
    VOL_5M_SEV4,
    VOL_5M_SEV5,
    VWAP_CROSS_SEV3_5M,
)
from market_sentinel.intelligence.contract import EpisodeCallBudget
from market_sentinel.intelligence.router import RouterPolicy
from market_sentinel.orchestration.warming import (
    HOT_CHANGE_5M,
    HOT_EVENT_SEVERITY,
    HOT_VOLUME_RATIO_5M,
    WARM_CHANGE_1M,
    WARM_CHANGE_5M,
    WARM_VOLUME_RATIO,
    WarmingConfig,
)
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.signals.cluster import CLUSTER_LOOKBACK_S
from market_sentinel.signals.cooldown import DEFAULT_COOLDOWN_S
from market_sentinel.telemetry.contract import TELEMETRY_DENYLIST, project_allowlist

ParameterStatus = Literal["supported", "deferred"]

_FROZEN_MONOTONIC_REASON = (
    "Current deterministic M5 Replay freezes monotonic time. "
    "Absolute cooldown/dwell seconds are not faithfully comparable."
)
_INTEL_NOT_ATTACHED_REASON = (
    "M5 comparator does not attach Intelligence; "
    "parameter cannot affect current comparison execution."
)
_LIVE_CADENCE_REASON = (
    "Replay corpus fetches every fixture tick with 0 intervals; "
    "live AdaptiveScheduler cadence is not Replay-comparable."
)
_EVENT_MODULE_GLOBAL_REASON = (
    "Event rule module global; requires EventThresholds injection across rules"
)

OFFLINE_TUNING_CONFIG_ALLOWLIST: frozenset[str] = frozenset(
    {
        "cluster_lookback_s",
        "hot_event_severity",
        "hot_volume_ratio_5m",
        "hot_change_5m",
        "warm_change_1m",
        "warm_change_5m",
        "warm_volume_ratio",
    }
)

DEFERRED_TUNING_PARAMETER_NAMES: frozenset[str] = frozenset(
    {
        "cooldown_s",
        "upgrade_dwell_s",
        "hot_downgrade_dwell_s",
        "warm_downgrade_dwell_s",
        "router_min_priority",
        "router_require_alert_edge",
        "router_min_convergence_types",
        "episode_max_calls",
        "allow_escalation_recall",
        "cold_interval_s",
        "warm_interval_s",
        "hot_interval_s",
        "rapid_1m_sev2",
        "rapid_1m_sev3",
        "rapid_1m_sev4",
        "rapid_5m_sev3",
        "rapid_5m_sev4",
        "rapid_5m_sev5",
        "vol_5m_sev2",
        "vol_5m_sev3",
        "vol_1m_sev3",
        "vol_5m_sev4",
        "vol_5m_sev5",
        "breakout_sev4",
        "breakout_sev5",
        "vwap_cross_sev3_5m",
        "ttl_short_s",
        "ttl_long_s",
        "prompt_compactness",
        "intelligence_timeout_s",
        "volume_ratio_lookback",
    }
)


@dataclass(frozen=True)
class TuningParameterInventory:
    name: str
    status: ParameterStatus
    production_default: object
    reason: str


def tuning_parameter_inventory() -> tuple[TuningParameterInventory, ...]:
    scheduler = SchedulerPolicy()
    router = RouterPolicy()
    budget = EpisodeCallBudget()
    return (
        TuningParameterInventory(
            "cluster_lookback_s",
            "supported",
            CLUSTER_LOOKBACK_S,
            "SignalComposer lookback_s; comparator observes signal_episodes_created",
        ),
        TuningParameterInventory(
            "hot_event_severity",
            "supported",
            HOT_EVENT_SEVERITY,
            "WarmingConfig via WarmingPolicy; comparator observes scheduler tick counts",
        ),
        TuningParameterInventory(
            "hot_volume_ratio_5m",
            "supported",
            HOT_VOLUME_RATIO_5M,
            "WarmingConfig via WarmingPolicy; comparator observes scheduler tick counts",
        ),
        TuningParameterInventory(
            "hot_change_5m",
            "supported",
            HOT_CHANGE_5M,
            "WarmingConfig via WarmingPolicy; comparator observes scheduler tick counts",
        ),
        TuningParameterInventory(
            "warm_change_1m",
            "supported",
            WARM_CHANGE_1M,
            "WarmingConfig via WarmingPolicy; comparator observes scheduler tick counts",
        ),
        TuningParameterInventory(
            "warm_change_5m",
            "supported",
            WARM_CHANGE_5M,
            "WarmingConfig via WarmingPolicy; comparator observes scheduler tick counts",
        ),
        TuningParameterInventory(
            "warm_volume_ratio",
            "supported",
            WARM_VOLUME_RATIO,
            "WarmingConfig via WarmingPolicy; comparator observes scheduler tick counts",
        ),
        TuningParameterInventory(
            "cooldown_s",
            "deferred",
            DEFAULT_COOLDOWN_S,
            _FROZEN_MONOTONIC_REASON,
        ),
        TuningParameterInventory(
            "upgrade_dwell_s",
            "deferred",
            scheduler.upgrade_dwell_s,
            _FROZEN_MONOTONIC_REASON,
        ),
        TuningParameterInventory(
            "hot_downgrade_dwell_s",
            "deferred",
            scheduler.hot_downgrade_dwell_s,
            _FROZEN_MONOTONIC_REASON,
        ),
        TuningParameterInventory(
            "warm_downgrade_dwell_s",
            "deferred",
            scheduler.warm_downgrade_dwell_s,
            _FROZEN_MONOTONIC_REASON,
        ),
        TuningParameterInventory(
            "router_min_priority",
            "deferred",
            router.min_priority.value,
            _INTEL_NOT_ATTACHED_REASON,
        ),
        TuningParameterInventory(
            "router_require_alert_edge",
            "deferred",
            router.require_alert_edge,
            _INTEL_NOT_ATTACHED_REASON,
        ),
        TuningParameterInventory(
            "router_min_convergence_types",
            "deferred",
            router.min_convergence_types,
            _INTEL_NOT_ATTACHED_REASON,
        ),
        TuningParameterInventory(
            "episode_max_calls",
            "deferred",
            budget.max_calls,
            _INTEL_NOT_ATTACHED_REASON,
        ),
        TuningParameterInventory(
            "allow_escalation_recall",
            "deferred",
            budget.allow_escalation_recall,
            _INTEL_NOT_ATTACHED_REASON,
        ),
        TuningParameterInventory(
            "cold_interval_s",
            "deferred",
            scheduler.cold_interval_s,
            _LIVE_CADENCE_REASON,
        ),
        TuningParameterInventory(
            "warm_interval_s",
            "deferred",
            scheduler.warm_interval_s,
            _LIVE_CADENCE_REASON,
        ),
        TuningParameterInventory(
            "hot_interval_s",
            "deferred",
            scheduler.hot_interval_s,
            _LIVE_CADENCE_REASON,
        ),
        TuningParameterInventory(
            "rapid_1m_sev2",
            "deferred",
            RAPID_1M_SEV2,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "rapid_1m_sev3",
            "deferred",
            RAPID_1M_SEV3,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "rapid_1m_sev4",
            "deferred",
            RAPID_1M_SEV4,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "rapid_5m_sev3",
            "deferred",
            RAPID_5M_SEV3,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "rapid_5m_sev4",
            "deferred",
            RAPID_5M_SEV4,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "rapid_5m_sev5",
            "deferred",
            RAPID_5M_SEV5,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "vol_5m_sev2",
            "deferred",
            VOL_5M_SEV2,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "vol_5m_sev3",
            "deferred",
            VOL_5M_SEV3,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "vol_1m_sev3",
            "deferred",
            VOL_1M_SEV3,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "vol_5m_sev4",
            "deferred",
            VOL_5M_SEV4,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "vol_5m_sev5",
            "deferred",
            VOL_5M_SEV5,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "breakout_sev4",
            "deferred",
            BREAKOUT_SEV4,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "breakout_sev5",
            "deferred",
            BREAKOUT_SEV5,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "vwap_cross_sev3_5m",
            "deferred",
            VWAP_CROSS_SEV3_5M,
            _EVENT_MODULE_GLOBAL_REASON,
        ),
        TuningParameterInventory(
            "ttl_short_s",
            "deferred",
            TTL_SHORT_S,
            "Event TTL module global; requires EventThresholds injection across rules",
        ),
        TuningParameterInventory(
            "ttl_long_s",
            "deferred",
            TTL_LONG_S,
            "Event TTL module global; requires EventThresholds injection across rules",
        ),
        TuningParameterInventory(
            "prompt_compactness",
            "deferred",
            None,
            "Intelligence payload shaping is not a typed injectable Offline Replay field",
        ),
        TuningParameterInventory(
            "intelligence_timeout_s",
            "deferred",
            None,
            "Coordinator timeout; M5 comparator does not attach Intelligence",
        ),
        TuningParameterInventory(
            "volume_ratio_lookback",
            "deferred",
            20,
            "FeatureEngine rolling window; not injected without FeaturePolicy refactor",
        ),
    )


def _finite_float(
    value: object,
    field: str,
    *,
    min_exclusive: float | None = None,
    min_inclusive: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TuningConfigError(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise TuningConfigError(f"{field} must be finite")
    if min_exclusive is not None and number <= min_exclusive:
        raise TuningConfigError(f"{field} must be > {min_exclusive}")
    if min_inclusive is not None and number < min_inclusive:
        raise TuningConfigError(f"{field} must be >= {min_inclusive}")
    return number


def _strict_int(value: object, field: str, *, min_inclusive: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TuningConfigError(f"{field} must be an int")
    if value < min_inclusive:
        raise TuningConfigError(f"{field} must be >= {min_inclusive}")
    return value


@dataclass(frozen=True)
class OfflineTuningConfig:
    """Candidate parameter body. Not TuningSnapshot identity. No arbitrary keys."""

    cluster_lookback_s: float
    hot_event_severity: int
    hot_volume_ratio_5m: float
    hot_change_5m: float
    warm_change_1m: float
    warm_change_5m: float
    warm_volume_ratio: float

    def __post_init__(self) -> None:
        _finite_float(self.cluster_lookback_s, "cluster_lookback_s", min_exclusive=0.0)
        if isinstance(self.hot_event_severity, bool) or not isinstance(
            self.hot_event_severity, int
        ):
            raise TuningConfigError("hot_event_severity must be an int")
        if self.hot_event_severity < 1 or self.hot_event_severity > 5:
            raise TuningConfigError("hot_event_severity must be 1..5")
        _finite_float(self.hot_volume_ratio_5m, "hot_volume_ratio_5m", min_exclusive=0.0)
        _finite_float(self.hot_change_5m, "hot_change_5m", min_exclusive=0.0)
        _finite_float(self.warm_change_1m, "warm_change_1m", min_exclusive=0.0)
        _finite_float(self.warm_change_5m, "warm_change_5m", min_exclusive=0.0)
        _finite_float(self.warm_volume_ratio, "warm_volume_ratio", min_exclusive=0.0)

    def to_record(self) -> dict[str, Any]:
        raw = {
            "cluster_lookback_s": self.cluster_lookback_s,
            "hot_event_severity": self.hot_event_severity,
            "hot_volume_ratio_5m": self.hot_volume_ratio_5m,
            "hot_change_5m": self.hot_change_5m,
            "warm_change_1m": self.warm_change_1m,
            "warm_change_5m": self.warm_change_5m,
            "warm_volume_ratio": self.warm_volume_ratio,
        }
        denied = TELEMETRY_DENYLIST.intersection(raw)
        if denied:
            raise TuningConfigError(f"denied keys: {sorted(denied)}")
        return project_allowlist(raw, OFFLINE_TUNING_CONFIG_ALLOWLIST)

    @classmethod
    def from_record(cls, payload: object) -> OfflineTuningConfig:
        if not isinstance(payload, dict):
            raise TuningConfigError("OfflineTuningConfig must be a JSON object")
        deferred = set(payload) & DEFERRED_TUNING_PARAMETER_NAMES
        if deferred:
            raise TuningConfigError("deferred parameters cannot enter OfflineTuningConfig")
        unknown = set(payload) - OFFLINE_TUNING_CONFIG_ALLOWLIST
        if unknown:
            raise TuningConfigError("unknown OfflineTuningConfig keys")
        missing = OFFLINE_TUNING_CONFIG_ALLOWLIST - set(payload)
        if missing:
            raise TuningConfigError("missing OfflineTuningConfig keys")
        severity = _strict_int(payload["hot_event_severity"], "hot_event_severity", min_inclusive=1)
        if severity > 5:
            raise TuningConfigError("hot_event_severity must be 1..5")
        return cls(
            cluster_lookback_s=_finite_float(
                payload["cluster_lookback_s"], "cluster_lookback_s", min_exclusive=0.0
            ),
            hot_event_severity=severity,
            hot_volume_ratio_5m=_finite_float(
                payload["hot_volume_ratio_5m"], "hot_volume_ratio_5m", min_exclusive=0.0
            ),
            hot_change_5m=_finite_float(
                payload["hot_change_5m"], "hot_change_5m", min_exclusive=0.0
            ),
            warm_change_1m=_finite_float(
                payload["warm_change_1m"], "warm_change_1m", min_exclusive=0.0
            ),
            warm_change_5m=_finite_float(
                payload["warm_change_5m"], "warm_change_5m", min_exclusive=0.0
            ),
            warm_volume_ratio=_finite_float(
                payload["warm_volume_ratio"], "warm_volume_ratio", min_exclusive=0.0
            ),
        )

    def warming_config(self) -> WarmingConfig:
        return WarmingConfig(
            hot_event_severity=self.hot_event_severity,
            hot_volume_ratio_5m=self.hot_volume_ratio_5m,
            hot_change_5m=self.hot_change_5m,
            warm_change_1m=self.warm_change_1m,
            warm_change_5m=self.warm_change_5m,
            warm_volume_ratio=self.warm_volume_ratio,
        )


def capture_baseline_config() -> OfflineTuningConfig:
    """Map current HEAD production defaults. Do not hand-copy a second table in tests."""
    warming = WarmingConfig()
    return OfflineTuningConfig(
        cluster_lookback_s=CLUSTER_LOOKBACK_S,
        hot_event_severity=warming.hot_event_severity,
        hot_volume_ratio_5m=warming.hot_volume_ratio_5m,
        hot_change_5m=warming.hot_change_5m,
        warm_change_1m=warming.warm_change_1m,
        warm_change_5m=warming.warm_change_5m,
        warm_volume_ratio=warming.warm_volume_ratio,
    )

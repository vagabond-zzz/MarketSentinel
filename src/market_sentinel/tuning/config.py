from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from market_sentinel.domain.enums import SignalPriority
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

OFFLINE_TUNING_CONFIG_ALLOWLIST: frozenset[str] = frozenset(
    {
        "cooldown_s",
        "cluster_lookback_s",
        "upgrade_dwell_s",
        "hot_downgrade_dwell_s",
        "warm_downgrade_dwell_s",
        "hot_event_severity",
        "hot_volume_ratio_5m",
        "hot_change_5m",
        "warm_change_1m",
        "warm_change_5m",
        "warm_volume_ratio",
        "router_min_priority",
        "router_require_alert_edge",
        "router_min_convergence_types",
        "episode_max_calls",
        "allow_escalation_recall",
    }
)

DEFERRED_TUNING_PARAMETER_NAMES: frozenset[str] = frozenset(
    {
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
            "cooldown_s",
            "supported",
            DEFAULT_COOLDOWN_S,
            "CooldownGate constructor injection; default DEFAULT_COOLDOWN_S",
        ),
        TuningParameterInventory(
            "cluster_lookback_s",
            "supported",
            CLUSTER_LOOKBACK_S,
            "SignalComposer lookback_s; default CLUSTER_LOOKBACK_S",
        ),
        TuningParameterInventory(
            "upgrade_dwell_s",
            "supported",
            scheduler.upgrade_dwell_s,
            "SchedulerPolicy.upgrade_dwell_s; Replay corpus still uses 0 poll intervals",
        ),
        TuningParameterInventory(
            "hot_downgrade_dwell_s",
            "supported",
            scheduler.hot_downgrade_dwell_s,
            "SchedulerPolicy.hot_downgrade_dwell_s",
        ),
        TuningParameterInventory(
            "warm_downgrade_dwell_s",
            "supported",
            scheduler.warm_downgrade_dwell_s,
            "SchedulerPolicy.warm_downgrade_dwell_s",
        ),
        TuningParameterInventory(
            "hot_event_severity",
            "supported",
            HOT_EVENT_SEVERITY,
            "WarmingConfig via WarmingPolicy(config=...); default module constant",
        ),
        TuningParameterInventory(
            "hot_volume_ratio_5m",
            "supported",
            HOT_VOLUME_RATIO_5M,
            "WarmingConfig constructor injection",
        ),
        TuningParameterInventory(
            "hot_change_5m",
            "supported",
            HOT_CHANGE_5M,
            "WarmingConfig constructor injection",
        ),
        TuningParameterInventory(
            "warm_change_1m",
            "supported",
            WARM_CHANGE_1M,
            "WarmingConfig constructor injection",
        ),
        TuningParameterInventory(
            "warm_change_5m",
            "supported",
            WARM_CHANGE_5M,
            "WarmingConfig constructor injection",
        ),
        TuningParameterInventory(
            "warm_volume_ratio",
            "supported",
            WARM_VOLUME_RATIO,
            "WarmingConfig constructor injection",
        ),
        TuningParameterInventory(
            "router_min_priority",
            "supported",
            router.min_priority.value,
            "RouterPolicy.min_priority; unused unless Intelligence is attached",
        ),
        TuningParameterInventory(
            "router_require_alert_edge",
            "supported",
            router.require_alert_edge,
            "RouterPolicy.require_alert_edge",
        ),
        TuningParameterInventory(
            "router_min_convergence_types",
            "supported",
            router.min_convergence_types,
            "RouterPolicy.min_convergence_types",
        ),
        TuningParameterInventory(
            "episode_max_calls",
            "supported",
            budget.max_calls,
            "EpisodeCallBudget.max_calls",
        ),
        TuningParameterInventory(
            "allow_escalation_recall",
            "supported",
            budget.allow_escalation_recall,
            "EpisodeCallBudget.allow_escalation_recall",
        ),
        TuningParameterInventory(
            "cold_interval_s",
            "deferred",
            scheduler.cold_interval_s,
            "Replay corpus fetches every fixture tick with 0 intervals; not Replay-comparable",
        ),
        TuningParameterInventory(
            "warm_interval_s",
            "deferred",
            scheduler.warm_interval_s,
            "Live AdaptiveScheduler cadence; deferred with cold_interval_s",
        ),
        TuningParameterInventory(
            "hot_interval_s",
            "deferred",
            scheduler.hot_interval_s,
            "Live AdaptiveScheduler cadence; deferred with cold_interval_s",
        ),
        TuningParameterInventory(
            "rapid_1m_sev2",
            "deferred",
            RAPID_1M_SEV2,
            "Event rule module global; requires EventThresholds injection across rules",
        ),
        TuningParameterInventory(
            "rapid_1m_sev3",
            "deferred",
            RAPID_1M_SEV3,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "rapid_1m_sev4",
            "deferred",
            RAPID_1M_SEV4,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "rapid_5m_sev3",
            "deferred",
            RAPID_5M_SEV3,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "rapid_5m_sev4",
            "deferred",
            RAPID_5M_SEV4,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "rapid_5m_sev5",
            "deferred",
            RAPID_5M_SEV5,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "vol_5m_sev2",
            "deferred",
            VOL_5M_SEV2,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "vol_5m_sev3",
            "deferred",
            VOL_5M_SEV3,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "vol_1m_sev3",
            "deferred",
            VOL_1M_SEV3,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "vol_5m_sev4",
            "deferred",
            VOL_5M_SEV4,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "vol_5m_sev5",
            "deferred",
            VOL_5M_SEV5,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "breakout_sev4",
            "deferred",
            BREAKOUT_SEV4,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "breakout_sev5",
            "deferred",
            BREAKOUT_SEV5,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "vwap_cross_sev3_5m",
            "deferred",
            VWAP_CROSS_SEV3_5M,
            "Event rule module global",
        ),
        TuningParameterInventory(
            "ttl_short_s",
            "deferred",
            TTL_SHORT_S,
            "Event TTL module global",
        ),
        TuningParameterInventory(
            "ttl_long_s",
            "deferred",
            TTL_LONG_S,
            "Event TTL module global",
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
            "Coordinator timeout; M5 comparator does not call a model",
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


def _strict_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise TuningConfigError(f"{field} must be a bool")
    return value


@dataclass(frozen=True)
class OfflineTuningConfig:
    """Candidate parameter body. Not TuningSnapshot identity. No arbitrary keys."""

    cooldown_s: float
    cluster_lookback_s: float
    upgrade_dwell_s: float
    hot_downgrade_dwell_s: float
    warm_downgrade_dwell_s: float
    hot_event_severity: int
    hot_volume_ratio_5m: float
    hot_change_5m: float
    warm_change_1m: float
    warm_change_5m: float
    warm_volume_ratio: float
    router_min_priority: SignalPriority
    router_require_alert_edge: bool
    router_min_convergence_types: int
    episode_max_calls: int
    allow_escalation_recall: bool

    def __post_init__(self) -> None:
        _finite_float(self.cooldown_s, "cooldown_s", min_exclusive=0.0)
        _finite_float(self.cluster_lookback_s, "cluster_lookback_s", min_exclusive=0.0)
        _finite_float(self.upgrade_dwell_s, "upgrade_dwell_s", min_inclusive=0.0)
        _finite_float(self.hot_downgrade_dwell_s, "hot_downgrade_dwell_s", min_exclusive=0.0)
        _finite_float(self.warm_downgrade_dwell_s, "warm_downgrade_dwell_s", min_exclusive=0.0)
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
        if not isinstance(self.router_min_priority, SignalPriority):
            raise TuningConfigError("router_min_priority must be a SignalPriority member")
        _strict_bool(self.router_require_alert_edge, "router_require_alert_edge")
        _strict_int(
            self.router_min_convergence_types, "router_min_convergence_types", min_inclusive=1
        )
        _strict_int(self.episode_max_calls, "episode_max_calls", min_inclusive=1)
        _strict_bool(self.allow_escalation_recall, "allow_escalation_recall")

    def to_record(self) -> dict[str, Any]:
        raw = {
            "cooldown_s": self.cooldown_s,
            "cluster_lookback_s": self.cluster_lookback_s,
            "upgrade_dwell_s": self.upgrade_dwell_s,
            "hot_downgrade_dwell_s": self.hot_downgrade_dwell_s,
            "warm_downgrade_dwell_s": self.warm_downgrade_dwell_s,
            "hot_event_severity": self.hot_event_severity,
            "hot_volume_ratio_5m": self.hot_volume_ratio_5m,
            "hot_change_5m": self.hot_change_5m,
            "warm_change_1m": self.warm_change_1m,
            "warm_change_5m": self.warm_change_5m,
            "warm_volume_ratio": self.warm_volume_ratio,
            "router_min_priority": self.router_min_priority.value,
            "router_require_alert_edge": self.router_require_alert_edge,
            "router_min_convergence_types": self.router_min_convergence_types,
            "episode_max_calls": self.episode_max_calls,
            "allow_escalation_recall": self.allow_escalation_recall,
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
        try:
            priority = SignalPriority(str(payload["router_min_priority"]))
        except ValueError as exc:
            raise TuningConfigError("invalid router_min_priority") from exc
        return cls(
            cooldown_s=_finite_float(payload["cooldown_s"], "cooldown_s", min_exclusive=0.0),
            cluster_lookback_s=_finite_float(
                payload["cluster_lookback_s"], "cluster_lookback_s", min_exclusive=0.0
            ),
            upgrade_dwell_s=_finite_float(
                payload["upgrade_dwell_s"], "upgrade_dwell_s", min_inclusive=0.0
            ),
            hot_downgrade_dwell_s=_finite_float(
                payload["hot_downgrade_dwell_s"], "hot_downgrade_dwell_s", min_exclusive=0.0
            ),
            warm_downgrade_dwell_s=_finite_float(
                payload["warm_downgrade_dwell_s"], "warm_downgrade_dwell_s", min_exclusive=0.0
            ),
            hot_event_severity=_strict_int(
                payload["hot_event_severity"], "hot_event_severity", min_inclusive=1
            ),
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
            router_min_priority=priority,
            router_require_alert_edge=_strict_bool(
                payload["router_require_alert_edge"], "router_require_alert_edge"
            ),
            router_min_convergence_types=_strict_int(
                payload["router_min_convergence_types"],
                "router_min_convergence_types",
                min_inclusive=1,
            ),
            episode_max_calls=_strict_int(
                payload["episode_max_calls"], "episode_max_calls", min_inclusive=1
            ),
            allow_escalation_recall=_strict_bool(
                payload["allow_escalation_recall"], "allow_escalation_recall"
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

    def scheduler_policy_for_replay(self) -> SchedulerPolicy:
        """Replay corpus procedure: always-due poll intervals; dwells from this config."""
        return SchedulerPolicy(
            cold_interval_s=0.0,
            warm_interval_s=0.0,
            hot_interval_s=0.0,
            upgrade_dwell_s=self.upgrade_dwell_s,
            hot_downgrade_dwell_s=self.hot_downgrade_dwell_s,
            warm_downgrade_dwell_s=self.warm_downgrade_dwell_s,
        )

    def router_policy(self) -> RouterPolicy:
        return RouterPolicy(
            min_priority=self.router_min_priority,
            require_alert_edge=self.router_require_alert_edge,
            min_convergence_types=self.router_min_convergence_types,
        )

    def episode_budget(self) -> EpisodeCallBudget:
        return EpisodeCallBudget(
            max_calls=self.episode_max_calls,
            allow_escalation_recall=self.allow_escalation_recall,
        )


def capture_baseline_config() -> OfflineTuningConfig:
    """Map current HEAD production defaults. Do not hand-copy a second table in tests."""
    scheduler = SchedulerPolicy()
    router = RouterPolicy()
    budget = EpisodeCallBudget()
    warming = WarmingConfig()
    return OfflineTuningConfig(
        cooldown_s=DEFAULT_COOLDOWN_S,
        cluster_lookback_s=CLUSTER_LOOKBACK_S,
        upgrade_dwell_s=scheduler.upgrade_dwell_s,
        hot_downgrade_dwell_s=scheduler.hot_downgrade_dwell_s,
        warm_downgrade_dwell_s=scheduler.warm_downgrade_dwell_s,
        hot_event_severity=warming.hot_event_severity,
        hot_volume_ratio_5m=warming.hot_volume_ratio_5m,
        hot_change_5m=warming.hot_change_5m,
        warm_change_1m=warming.warm_change_1m,
        warm_change_5m=warming.warm_change_5m,
        warm_volume_ratio=warming.warm_volume_ratio,
        router_min_priority=router.min_priority,
        router_require_alert_edge=router.require_alert_edge,
        router_min_convergence_types=router.min_convergence_types,
        episode_max_calls=budget.max_calls,
        allow_escalation_recall=budget.allow_escalation_recall,
    )

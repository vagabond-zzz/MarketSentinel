from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_sentinel.telemetry.contract import TELEMETRY_DENYLIST

TUNING_COMPARISON_SCHEMA_VERSION = 2

UNAVAILABLE_HOST_OFFLINE = "host_not_in_offline_replay"
UNAVAILABLE_INTEL_OFFLINE = "intelligence_not_in_offline_replay"

RECOMMENDATION_DENIED_KEYS: frozenset[str] = frozenset(
    {
        "recommended",
        "optimal",
        "better",
        "best",
        "ship",
        "winner",
        "score",
        "rank",
        "approve",
        "apply",
        "promote",
        "activate",
        "deploy",
    }
)

TUNING_COMPARISON_ALLOWLIST: frozenset[str] = frozenset(
    {
        "schema_version",
        "baseline_snapshot",
        "candidate_snapshot",
        "baseline_config",
        "candidate_config",
        "corpus",
        "baseline_metrics",
        "candidate_metrics",
        "delta",
        "feedback_evidence",
        "data_quality",
        "per_fixture",
        "corpus_id",
        "snapshot_id",
        "created_timestamp",
        "source",
        "config_version",
        "pipeline",
        "noise",
        "scheduler",
        "intelligence",
        "cold_tick_count",
        "warm_tick_count",
        "hot_tick_count",
        "level_transition_count",
        "processed_tick_count",
        "events_generated",
        "events_deduped",
        "events_clustered",
        "signal_episodes_created",
        "signal_escalations",
        "alert_candidates",
        "alert_suppressed",
        "alerts_presented",
        "info_count",
        "notice_count",
        "important_count",
        "critical_count",
        "suppression_by_reason",
        "cooldown",
        "same_tick_duplicate",
        "repeated_episode_signal_count",
        "repeated_episode_extra_alert_count",
        "alerts_per_market_hour",
        "available",
        "value",
        "unavailable_reason",
        "producer",
        "baseline",
        "candidate",
        "delta",
        "raw_feedback_count",
        "semantic_valid_feedback_count",
        "eligible_target_count",
        "orphan_feedback_count",
        "superseded_feedback_count",
        "useful",
        "not_useful",
        "too_noisy",
        "too_late",
        "orphan_count",
        "snapshot_valid",
        "wrote_telemetry_jsonl",
        "wrote_feedback_jsonl",
        "cluster_lookback_s",
        "hot_event_severity",
        "hot_volume_ratio_5m",
        "hot_change_5m",
        "warm_change_1m",
        "warm_change_5m",
        "warm_volume_ratio",
        "facts_match",
    }
)


def unavailable_metric(reason: str) -> dict[str, object]:
    return {
        "available": False,
        "value": None,
        "unavailable_reason": reason,
        "producer": None,
    }


def _all_keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        found.update(payload)
        for value in payload.values():
            found.update(_all_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_all_keys(item))
    return found


def _project_tree(payload: object) -> object:
    if isinstance(payload, dict):
        denied = TELEMETRY_DENYLIST.intersection(payload) | (
            RECOMMENDATION_DENIED_KEYS.intersection(payload)
        )
        if denied:
            raise ValueError(f"tuning comparison contains denied keys: {sorted(denied)}")
        projected: dict[str, object] = {}
        for key, value in payload.items():
            if key not in TUNING_COMPARISON_ALLOWLIST:
                continue
            projected[key] = _project_tree(value)
        return projected
    if isinstance(payload, list):
        return [_project_tree(item) for item in payload]
    return payload


def sanitize_comparison(payload: dict[str, Any]) -> dict[str, Any]:
    denied = TELEMETRY_DENYLIST.intersection(_all_keys(payload))
    if denied:
        raise ValueError(f"tuning comparison contains denied keys: {sorted(denied)}")
    banned = RECOMMENDATION_DENIED_KEYS.intersection(_all_keys(payload))
    if banned:
        raise ValueError(f"tuning comparison contains recommendation keys: {sorted(banned)}")
    return _project_tree(payload)  # type: ignore[return-value]


@dataclass(frozen=True)
class TuningComparisonReport:
    """Machine-readable before/after facts. Not an approval, score, or production write."""

    schema_version: int
    baseline_snapshot: dict[str, Any]
    candidate_snapshot: dict[str, Any]
    baseline_config: dict[str, Any]
    candidate_config: dict[str, Any]
    corpus: list[str]
    baseline_metrics: dict[str, Any]
    candidate_metrics: dict[str, Any]
    delta: dict[str, Any]
    feedback_evidence: dict[str, Any]
    data_quality: dict[str, Any]
    per_fixture: list[dict[str, Any]]

    def to_record(self) -> dict[str, Any]:
        raw = {
            "schema_version": self.schema_version,
            "baseline_snapshot": self.baseline_snapshot,
            "candidate_snapshot": self.candidate_snapshot,
            "baseline_config": self.baseline_config,
            "candidate_config": self.candidate_config,
            "corpus": list(self.corpus),
            "baseline_metrics": self.baseline_metrics,
            "candidate_metrics": self.candidate_metrics,
            "delta": self.delta,
            "feedback_evidence": self.feedback_evidence,
            "data_quality": self.data_quality,
            "per_fixture": self.per_fixture,
        }
        return sanitize_comparison(raw)

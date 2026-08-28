from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_sentinel.intelligence.contract import FallbackReason
from market_sentinel.telemetry.contract import (
    TELEMETRY_DENYLIST,
    DecisionReason,
    SuppressionReason,
    project_allowlist,
)

EVALUATION_ALLOWLIST: frozenset[str] = frozenset(
    {
        "metadata",
        "data_quality",
        "pipeline",
        "alert_noise",
        "host_interaction",
        "intelligence",
        "per_symbol",
        "per_run",
        "per_market_date",
        "explicit_feedback",
        "run_ids",
        "symbols",
        "market_dates",
        "filter_run_id",
        "input_files",
        "records_read",
        "malformed_complete_lines",
        "skipped_trailing_partial",
        "healthy",
        "data_quality_warning",
        "semantic_warning_count",
        "runs_insufficient_market_time",
        "runs_unsupported_market_scope",
        "market_time_coverage",
        "min_market_timestamp",
        "max_market_timestamp",
        "observed_market_seconds",
        "events_generated",
        "events_deduped",
        "events_clustered",
        "signal_episodes_created",
        "signal_escalations",
        "alert_candidates",
        "alert_suppressed",
        "alerts_presented",
        "cluster_tracker_seen_count",
        "dedupe_rate",
        "event_to_signal_rate",
        "signal_to_alert_candidate_rate",
        "candidate_to_presented_rate",
        "alert_suppression_rate",
        "info_count",
        "notice_count",
        "important_count",
        "critical_count",
        "important_critical_ratio",
        "alerts_per_market_hour",
        "repeated_episode_signal_count",
        "repeated_episode_extra_alert_count",
        "suppression_by_reason",
        "cooldown",
        "same_tick_duplicate",
        "unrecognized_skip_reason_count",
        "unrecognized_fallback_reason_count",
        "unrecognized_suppression_reason_count",
        "alert_badge_reset",
        "signal_opened",
        "alert_dismissed",
        "signal_muted",
        "open_rate",
        "dismiss_rate",
        "mute_rate",
        "explicit_feedback",
        "feedback_count",
        "useful_count",
        "not_useful_count",
        "too_noisy_count",
        "too_late_count",
        "useful_rate",
        "feedback_coverage",
        "available",
        "value",
        "unavailable_reason",
        "producer",
        "routed",
        "skipped",
        "succeeded",
        "fallback",
        "skip_by_decision_reason",
        "fallback_by_fallback_reason",
        "latency",
        "token_usage",
        "router",
        "model",
        "parse",
        "stage",
        "count",
        "min_s",
        "median_s",
        "p95_s",
        "max_s",
        "token_in_total",
        "token_out_total",
        "token_total",
        "token_events_count",
        "symbol",
        "run_id",
        "market_date",
        "expired_episode",
        "suppressed_edge",
        "stale_feed",
        "insufficient_features",
        "not_candidate",
        "episode_budget",
        "none",
        "timeout",
        "transport",
        "malformed",
        "rate_limited",
        "unavailable",
        "cancelled",
        "stale_work",
        "policy",
    }
)

KNOWN_SKIP_REASONS: tuple[str, ...] = tuple(item.value for item in DecisionReason)
KNOWN_FALLBACK_REASONS: tuple[str, ...] = tuple(item.value for item in FallbackReason)
KNOWN_SUPPRESSION_REASONS: tuple[str, ...] = tuple(item.value for item in SuppressionReason)

UNAVAILABLE_DENOMINATOR_ZERO = "denominator_is_zero"
UNAVAILABLE_PRODUCER = "producer_not_implemented"
UNAVAILABLE_NO_USAGE = "no_provider_usage"
UNAVAILABLE_MARKET_TIME = "insufficient_market_time_evidence"
UNAVAILABLE_MARKET_SCOPE = "unsupported_market_scope"
UNAVAILABLE_NO_FEEDBACK = "no_explicit_feedback"

PRODUCER_SIGNAL_OPENED = "signal_opened"
PRODUCER_ALERT_DISMISSED = "alert_dismissed"
PRODUCER_SIGNAL_MUTED = "signal_muted"


def unavailable(reason: str, *, producer: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "available": False,
        "value": None,
        "unavailable_reason": reason,
        "producer": producer,
    }
    return project_allowlist(payload, EVALUATION_ALLOWLIST)


def available_value(value: float | int) -> dict[str, object]:
    return project_allowlist(
        {
            "available": True,
            "value": value,
            "unavailable_reason": None,
            "producer": None,
        },
        EVALUATION_ALLOWLIST,
    )


def sanitize_report(payload: dict[str, Any]) -> dict[str, Any]:
    denied = TELEMETRY_DENYLIST.intersection(_all_keys(payload))
    if denied:
        raise ValueError(f"evaluation report contains denied keys: {sorted(denied)}")
    return _project_tree(payload)


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
        denied = TELEMETRY_DENYLIST.intersection(payload)
        if denied:
            raise ValueError(f"evaluation report contains denied keys: {sorted(denied)}")
        projected: dict[str, object] = {}
        for key, value in payload.items():
            if key not in EVALUATION_ALLOWLIST:
                continue
            projected[key] = _project_tree(value)
        return projected
    if isinstance(payload, list):
        return [_project_tree(item) for item in payload]
    return payload


@dataclass(frozen=True)
class EvaluationReport:
    """Read-only evaluation. Not MarketState, not a tuning command, not Protocol."""

    metadata: dict[str, Any]
    data_quality: dict[str, Any]
    pipeline: dict[str, Any]
    alert_noise: dict[str, Any]
    host_interaction: dict[str, Any]
    intelligence: dict[str, Any]
    per_symbol: list[dict[str, Any]]
    per_run: list[dict[str, Any]]
    per_market_date: list[dict[str, Any]]
    explicit_feedback: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        raw = {
            "metadata": self.metadata,
            "data_quality": self.data_quality,
            "pipeline": self.pipeline,
            "alert_noise": self.alert_noise,
            "host_interaction": self.host_interaction,
            "intelligence": self.intelligence,
            "per_symbol": self.per_symbol,
            "per_run": self.per_run,
            "per_market_date": self.per_market_date,
            "explicit_feedback": self.explicit_feedback,
        }
        return sanitize_report(raw)

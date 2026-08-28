from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------


class TelemetryKind(StrEnum):
    PIPELINE = "pipeline"
    HOST = "host"
    INTELLIGENCE = "intelligence"


class TelemetryName(StrEnum):
    EVENT_GENERATED = "event_generated"
    EVENT_DEDUPED = "event_deduped"
    EVENT_CLUSTERED = "event_clustered"
    SIGNAL_EPISODE_CREATED = "signal_episode_created"
    SIGNAL_ESCALATED = "signal_escalated"
    ALERT_CANDIDATE = "alert_candidate"
    ALERT_PRESENTED = "alert_presented"
    SIGNAL_OPENED = "signal_opened"
    ALERT_BADGE_RESET = "alert_badge_reset"
    ALERT_DISMISSED = "alert_dismissed"
    SIGNAL_MUTED = "signal_muted"
    INTELLIGENCE_ROUTED = "intelligence_routed"
    INTELLIGENCE_SKIPPED = "intelligence_skipped"
    INTELLIGENCE_SUCCEEDED = "intelligence_succeeded"
    INTELLIGENCE_FALLBACK = "intelligence_fallback"
    INTELLIGENCE_TOKEN_USAGE = "intelligence_token_usage"
    INTELLIGENCE_LATENCY = "intelligence_latency"


class FeedbackLabel(StrEnum):
    USEFUL = "useful"
    NOT_USEFUL = "not_useful"
    TOO_NOISY = "too_noisy"
    TOO_LATE = "too_late"


class TuningSource(StrEnum):
    MANUAL = "manual"
    OFFLINE_EVAL = "offline_eval"


# ---------------------------------------------------------------------------
# Allow / deny
# ---------------------------------------------------------------------------

TELEMETRY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "telemetry_id",
        "name",
        "kind",
        "created_timestamp",
        "symbol",
        "event_id",
        "signal_id",
        "event_type",
        "family",
        "direction",
        "priority",
        "host_action",
        "intelligence_status",
        "fallback_reason",
        "latency_s",
        "token_in",
        "token_out",
    }
)

TELEMETRY_DENYLIST: frozenset[str] = frozenset(
    {
        "workspace",
        "source_code",
        "conversation",
        "files",
        "ticks",
        "snapshots",
        "ring_buffer",
        "features",
        "prompt",
        "api_key",
        "title",
        "summary",
        "reason",
        "event_ids",
        "rule_names",
        "priority_reason",
        "delete_event",
        "rewrite_threshold",
        "mutate_signal",
        "apply_online",
    }
)

FEEDBACK_ALLOWLIST: frozenset[str] = frozenset(
    {
        "feedback_id",
        "created_timestamp",
        "label",
        "symbol",
        "event_id",
        "signal_id",
        "telemetry_id",
    }
)

TUNING_ALLOWLIST: frozenset[str] = frozenset(
    {
        "snapshot_id",
        "created_timestamp",
        "source",
        "config_version",
        "notes",
    }
)

_KIND_FOR_NAME: dict[TelemetryName, TelemetryKind] = {
    TelemetryName.EVENT_GENERATED: TelemetryKind.PIPELINE,
    TelemetryName.EVENT_DEDUPED: TelemetryKind.PIPELINE,
    TelemetryName.EVENT_CLUSTERED: TelemetryKind.PIPELINE,
    TelemetryName.SIGNAL_EPISODE_CREATED: TelemetryKind.PIPELINE,
    TelemetryName.SIGNAL_ESCALATED: TelemetryKind.PIPELINE,
    TelemetryName.ALERT_CANDIDATE: TelemetryKind.PIPELINE,
    TelemetryName.ALERT_PRESENTED: TelemetryKind.HOST,
    TelemetryName.SIGNAL_OPENED: TelemetryKind.HOST,
    TelemetryName.ALERT_BADGE_RESET: TelemetryKind.HOST,
    TelemetryName.ALERT_DISMISSED: TelemetryKind.HOST,
    TelemetryName.SIGNAL_MUTED: TelemetryKind.HOST,
    TelemetryName.INTELLIGENCE_ROUTED: TelemetryKind.INTELLIGENCE,
    TelemetryName.INTELLIGENCE_SKIPPED: TelemetryKind.INTELLIGENCE,
    TelemetryName.INTELLIGENCE_SUCCEEDED: TelemetryKind.INTELLIGENCE,
    TelemetryName.INTELLIGENCE_FALLBACK: TelemetryKind.INTELLIGENCE,
    TelemetryName.INTELLIGENCE_TOKEN_USAGE: TelemetryKind.INTELLIGENCE,
    TelemetryName.INTELLIGENCE_LATENCY: TelemetryKind.INTELLIGENCE,
}


def kind_for(name: TelemetryName) -> TelemetryKind:
    return _KIND_FOR_NAME[name]


def _reject_denied(payload: dict[str, Any]) -> None:
    denied = TELEMETRY_DENYLIST.intersection(payload)
    if denied:
        raise ValueError(f"telemetry/feedback payload contains denied keys: {sorted(denied)}")


def project_allowlist(payload: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    _reject_denied(payload)
    return {key: value for key, value in payload.items() if key in allowed}


# ---------------------------------------------------------------------------
# Records (not MarketState, not Protocol DTOs, not storage rows)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelemetryEvent:
    """Append-only observation. Does not mutate Event, Signal, or production config."""

    telemetry_id: str
    name: TelemetryName
    kind: TelemetryKind
    created_timestamp: float
    symbol: str | None = None
    event_id: str | None = None
    signal_id: str | None = None
    event_type: str | None = None
    family: str | None = None
    direction: str | None = None
    priority: str | None = None
    host_action: str | None = None
    intelligence_status: str | None = None
    fallback_reason: str | None = None
    latency_s: float | None = None
    token_in: int | None = None
    token_out: int | None = None

    def __post_init__(self) -> None:
        expected = kind_for(self.name)
        if self.kind is not expected:
            raise ValueError(f"{self.name.value} must have kind={expected.value}")

    def to_record(self) -> dict[str, Any]:
        raw = {
            "telemetry_id": self.telemetry_id,
            "name": self.name.value,
            "kind": self.kind.value,
            "created_timestamp": self.created_timestamp,
            "symbol": self.symbol,
            "event_id": self.event_id,
            "signal_id": self.signal_id,
            "event_type": self.event_type,
            "family": self.family,
            "direction": self.direction,
            "priority": self.priority,
            "host_action": self.host_action,
            "intelligence_status": self.intelligence_status,
            "fallback_reason": self.fallback_reason,
            "latency_s": self.latency_s,
            "token_in": self.token_in,
            "token_out": self.token_out,
        }
        return project_allowlist(raw, TELEMETRY_ALLOWLIST)


@dataclass(frozen=True)
class UserFeedback:
    """Optional explicit opinion. Never a market fact and never a mutation command."""

    feedback_id: str
    created_timestamp: float
    label: FeedbackLabel
    symbol: str | None = None
    event_id: str | None = None
    signal_id: str | None = None
    telemetry_id: str | None = None

    def to_record(self) -> dict[str, Any]:
        raw = {
            "feedback_id": self.feedback_id,
            "created_timestamp": self.created_timestamp,
            "label": self.label.value,
            "symbol": self.symbol,
            "event_id": self.event_id,
            "signal_id": self.signal_id,
            "telemetry_id": self.telemetry_id,
        }
        return project_allowlist(raw, FEEDBACK_ALLOWLIST)


@dataclass(frozen=True)
class TuningSnapshot:
    """Versioned offline config identity. Has no apply-to-production API."""

    snapshot_id: str
    created_timestamp: float
    source: TuningSource
    config_version: str
    notes: str | None = None

    def to_record(self) -> dict[str, Any]:
        raw = {
            "snapshot_id": self.snapshot_id,
            "created_timestamp": self.created_timestamp,
            "source": self.source.value,
            "config_version": self.config_version,
            "notes": self.notes,
        }
        return project_allowlist(raw, TUNING_ALLOWLIST)

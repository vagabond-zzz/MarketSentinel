from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# Host produces interaction facts. Core owns the collector / future local log.
# M1: Host → additive Protocol v1 host-interaction command → Core collector.
# Not two independent telemetry databases. Storage schema != Protocol schema.
HOST_INTERACTION_FACT_OWNER = "host"
TELEMETRY_COLLECTOR_OWNER = "core"

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
    ALERT_SUPPRESSED = "alert_suppressed"
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


class SuppressionReason(StrEnum):
    """Why a composed Signal did not become an alert candidate. Not Event dedupe."""

    COOLDOWN = "cooldown"
    SAME_TICK_DUPLICATE = "same_tick_duplicate"


class DecisionReason(StrEnum):
    """Deterministic Router NO. Not a provider/model completion failure."""

    EXPIRED_EPISODE = "expired_episode"
    SUPPRESSED_EDGE = "suppressed_edge"
    STALE_FEED = "stale_feed"
    INSUFFICIENT_FEATURES = "insufficient_features"
    NOT_CANDIDATE = "not_candidate"
    EPISODE_BUDGET = "episode_budget"


class LatencyStage(StrEnum):
    ROUTER = "router"
    MODEL = "model"
    PARSE = "parse"


# ---------------------------------------------------------------------------
# Allow / deny
# ---------------------------------------------------------------------------

TELEMETRY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "telemetry_id",
        "name",
        "kind",
        "created_timestamp",
        "run_id",
        "market_timestamp",
        "symbol",
        "event_id",
        "signal_id",
        "event_type",
        "family",
        "direction",
        "priority",
        "host_action",
        "intelligence_status",
        "decision_reason",
        "fallback_reason",
        "suppression_reason",
        "latency_s",
        "latency_stage",
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
        "notes",
        "session_id",
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
        "run_id",
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
    }
)

_KIND_FOR_NAME: dict[TelemetryName, TelemetryKind] = {
    TelemetryName.EVENT_GENERATED: TelemetryKind.PIPELINE,
    TelemetryName.EVENT_DEDUPED: TelemetryKind.PIPELINE,
    TelemetryName.EVENT_CLUSTERED: TelemetryKind.PIPELINE,
    TelemetryName.SIGNAL_EPISODE_CREATED: TelemetryKind.PIPELINE,
    TelemetryName.SIGNAL_ESCALATED: TelemetryKind.PIPELINE,
    TelemetryName.ALERT_CANDIDATE: TelemetryKind.PIPELINE,
    TelemetryName.ALERT_SUPPRESSED: TelemetryKind.PIPELINE,
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

_EVENT_ID_NAMES = frozenset(
    {
        TelemetryName.EVENT_GENERATED,
        TelemetryName.EVENT_DEDUPED,
        TelemetryName.EVENT_CLUSTERED,
    }
)
_SIGNAL_SYMBOL_NAMES = frozenset(
    {
        TelemetryName.SIGNAL_EPISODE_CREATED,
        TelemetryName.SIGNAL_ESCALATED,
        TelemetryName.ALERT_CANDIDATE,
        TelemetryName.ALERT_SUPPRESSED,
    }
)
_HOST_SIGNAL_NAMES = frozenset(
    {
        TelemetryName.ALERT_PRESENTED,
        TelemetryName.SIGNAL_OPENED,
        TelemetryName.ALERT_DISMISSED,
        TelemetryName.SIGNAL_MUTED,
    }
)
_INTEL_NAMES = frozenset(
    {
        TelemetryName.INTELLIGENCE_ROUTED,
        TelemetryName.INTELLIGENCE_SKIPPED,
        TelemetryName.INTELLIGENCE_SUCCEEDED,
        TelemetryName.INTELLIGENCE_FALLBACK,
        TelemetryName.INTELLIGENCE_TOKEN_USAGE,
        TelemetryName.INTELLIGENCE_LATENCY,
    }
)


def kind_for(name: TelemetryName) -> TelemetryKind:
    return _KIND_FOR_NAME[name]


def _reject_denied(payload: dict[str, Any]) -> None:
    denied = TELEMETRY_DENYLIST.intersection(payload)
    if denied:
        raise ValueError(f"telemetry/feedback payload contains denied keys: {sorted(denied)}")


def project_allowlist(payload: dict[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    _reject_denied(payload)
    return {key: value for key, value in payload.items() if key in allowed}


def _require_text(value: str, field: str) -> None:
    if value.strip() == "":
        raise ValueError(f"{field} must be non-empty")


def _require_finite(value: float, field: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")


def _require_non_negative(value: float | int, field: str) -> None:
    if value < 0:
        raise ValueError(f"{field} must be >= 0")


def _require_enum(value: object, enum_cls: type[StrEnum], field: str) -> None:
    if not isinstance(value, enum_cls):
        raise ValueError(f"{field} must be a {enum_cls.__name__} member")


# ---------------------------------------------------------------------------
# Cluster once-per-run helper (semantics frozen; M1 wires membership)
# ---------------------------------------------------------------------------


class ClusterMembershipTracker:
    """One event_id emits event_clustered at most once per run.

    First time the event participates in a multi-event Signal episode.
    Composer recomputes do not re-emit.
    """

    def __init__(self) -> None:
        self._clustered: set[str] = set()

    def newly_clustered(self, member_ids: Sequence[str]) -> tuple[str, ...]:
        unique = list(dict.fromkeys(member_ids))
        if len(unique) < 2:
            return ()
        fresh = tuple(event_id for event_id in unique if event_id not in self._clustered)
        self._clustered.update(fresh)
        return fresh


# ---------------------------------------------------------------------------
# Records (not MarketState, not Protocol DTOs, not storage rows)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TelemetryEvent:
    """Append-only observation. Does not mutate Event, Signal, or production config.

    created_timestamp = observation wall clock.
    market_timestamp = market time (pipeline/signal/intel); Host-only may be None.
    run_id = one Core runtime / Replay execution (not UTC+8 session_id()).
    alert_presented is produced by Host, collected by Core.
    """

    telemetry_id: str
    name: TelemetryName
    kind: TelemetryKind
    created_timestamp: float
    run_id: str
    market_timestamp: float | None = None
    symbol: str | None = None
    event_id: str | None = None
    signal_id: str | None = None
    event_type: str | None = None
    family: str | None = None
    direction: str | None = None
    priority: str | None = None
    host_action: str | None = None
    intelligence_status: str | None = None
    decision_reason: DecisionReason | None = None
    fallback_reason: str | None = None
    suppression_reason: SuppressionReason | None = None
    latency_s: float | None = None
    latency_stage: LatencyStage | None = None
    token_in: int | None = None
    token_out: int | None = None

    def __post_init__(self) -> None:
        expected = kind_for(self.name)
        if self.kind is not expected:
            raise ValueError(f"{self.name.value} must have kind={expected.value}")
        _require_text(self.telemetry_id, "telemetry_id")
        _require_text(self.run_id, "run_id")
        _require_finite(self.created_timestamp, "created_timestamp")
        if self.market_timestamp is not None:
            _require_finite(self.market_timestamp, "market_timestamp")
        if self.latency_s is not None:
            _require_finite(self.latency_s, "latency_s")
            _require_non_negative(self.latency_s, "latency_s")
        if self.token_in is not None:
            _require_non_negative(self.token_in, "token_in")
        if self.token_out is not None:
            _require_non_negative(self.token_out, "token_out")
        if self.decision_reason is not None:
            _require_enum(self.decision_reason, DecisionReason, "decision_reason")
        if self.fallback_reason is not None:
            _require_text(self.fallback_reason, "fallback_reason")
        if self.suppression_reason is not None:
            _require_enum(self.suppression_reason, SuppressionReason, "suppression_reason")
        if self.latency_stage is not None:
            _require_enum(self.latency_stage, LatencyStage, "latency_stage")
        self._validate_correlations()

    def _validate_correlations(self) -> None:
        name = self.name
        if name in _EVENT_ID_NAMES:
            if not self.event_id or not self.symbol:
                raise ValueError(f"{name.value} requires event_id and symbol")
        if name in _SIGNAL_SYMBOL_NAMES:
            if not self.signal_id or not self.symbol:
                raise ValueError(f"{name.value} requires signal_id and symbol")
        if name in _HOST_SIGNAL_NAMES:
            if not self.signal_id:
                raise ValueError(f"{name.value} requires signal_id")
        if name in _INTEL_NAMES:
            if not self.signal_id:
                raise ValueError(f"{name.value} requires signal_id")
        if name is TelemetryName.ALERT_SUPPRESSED:
            if self.suppression_reason is None:
                raise ValueError("alert_suppressed requires suppression_reason")
        if name is TelemetryName.INTELLIGENCE_SKIPPED:
            if self.decision_reason is None:
                raise ValueError("intelligence_skipped requires decision_reason")
            if self.fallback_reason is not None:
                raise ValueError("intelligence_skipped must not set fallback_reason")
        if name is TelemetryName.INTELLIGENCE_FALLBACK:
            if not self.fallback_reason:
                raise ValueError("intelligence_fallback requires fallback_reason")
            if self.decision_reason is not None:
                raise ValueError("intelligence_fallback must not set decision_reason")
        if name is TelemetryName.INTELLIGENCE_LATENCY:
            if self.latency_s is None or self.latency_stage is None:
                raise ValueError("intelligence_latency requires latency_s and latency_stage")
        if name is TelemetryName.INTELLIGENCE_TOKEN_USAGE:
            if self.token_in is None and self.token_out is None:
                raise ValueError("intelligence_token_usage requires provider token usage")

    def to_record(self) -> dict[str, Any]:
        raw = {
            "telemetry_id": self.telemetry_id,
            "name": self.name.value,
            "kind": self.kind.value,
            "created_timestamp": self.created_timestamp,
            "run_id": self.run_id,
            "market_timestamp": self.market_timestamp,
            "symbol": self.symbol,
            "event_id": self.event_id,
            "signal_id": self.signal_id,
            "event_type": self.event_type,
            "family": self.family,
            "direction": self.direction,
            "priority": self.priority,
            "host_action": self.host_action,
            "intelligence_status": self.intelligence_status,
            "decision_reason": None if self.decision_reason is None else self.decision_reason.value,
            "fallback_reason": self.fallback_reason,
            "suppression_reason": (
                None if self.suppression_reason is None else self.suppression_reason.value
            ),
            "latency_s": self.latency_s,
            "latency_stage": None if self.latency_stage is None else self.latency_stage.value,
            "token_in": self.token_in,
            "token_out": self.token_out,
        }
        return project_allowlist(raw, TELEMETRY_ALLOWLIST)


@dataclass(frozen=True)
class UserFeedback:
    """Optional explicit opinion. Never a market fact and never a mutation command."""

    feedback_id: str
    created_timestamp: float
    run_id: str
    label: FeedbackLabel
    symbol: str | None = None
    event_id: str | None = None
    signal_id: str | None = None
    telemetry_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.feedback_id, "feedback_id")
        _require_text(self.run_id, "run_id")
        _require_finite(self.created_timestamp, "created_timestamp")

    def to_record(self) -> dict[str, Any]:
        raw = {
            "feedback_id": self.feedback_id,
            "created_timestamp": self.created_timestamp,
            "run_id": self.run_id,
            "label": self.label.value,
            "symbol": self.symbol,
            "event_id": self.event_id,
            "signal_id": self.signal_id,
            "telemetry_id": self.telemetry_id,
        }
        return project_allowlist(raw, FEEDBACK_ALLOWLIST)


@dataclass(frozen=True)
class TuningSnapshot:
    """Versioned offline config identity. Has no apply-to-production API and no free text."""

    snapshot_id: str
    created_timestamp: float
    source: TuningSource
    config_version: str

    def __post_init__(self) -> None:
        _require_text(self.snapshot_id, "snapshot_id")
        _require_text(self.config_version, "config_version")
        _require_finite(self.created_timestamp, "created_timestamp")

    def to_record(self) -> dict[str, Any]:
        raw = {
            "snapshot_id": self.snapshot_id,
            "created_timestamp": self.created_timestamp,
            "source": self.source.value,
            "config_version": self.config_version,
        }
        return project_allowlist(raw, TUNING_ALLOWLIST)

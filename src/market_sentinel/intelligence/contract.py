from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from market_sentinel.domain.enums import EventDirection, FeedStatus, SignalPriority

_PRIORITY_RANK = {
    SignalPriority.INFO: 1,
    SignalPriority.NOTICE: 2,
    SignalPriority.IMPORTANT: 3,
    SignalPriority.CRITICAL: 4,
}


class IntelligenceStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    QUEUED = "queued"
    RUNNING = "running"
    ENRICHED = "enriched"
    FALLBACK = "fallback"


class FallbackReason(StrEnum):
    NONE = "none"
    NOT_CANDIDATE = "not_candidate"
    STALE_FEED = "stale_feed"
    INSUFFICIENT_FEATURES = "insufficient_features"
    SUPPRESSED_EDGE = "suppressed_edge"
    EPISODE_BUDGET = "episode_budget"
    EXPIRED_EPISODE = "expired_episode"
    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    MALFORMED = "malformed"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    STALE_WORK = "stale_work"
    POLICY = "policy"


@dataclass(frozen=True)
class IntelligenceInput:
    """Compressed structured facts for Router / model. Not a SignalTrace dump."""

    signal_id: str
    symbol: str
    family: str
    direction: EventDirection
    priority: SignalPriority
    event_types: tuple[str, ...]
    change_1m: float | None
    change_5m: float | None
    volume_ratio_5m: float | None
    above_vwap: bool | None
    rsi14: float | None
    day_range_position: float | None
    feed_status: FeedStatus
    alert_edge: bool
    episode_call_count: int
    last_requested_priority: SignalPriority | None
    expired: bool


@dataclass(frozen=True)
class IntelligenceAnnotation:
    signal_id: str
    worth_highlight: bool
    reason: str
    confidence: float
    summary: str
    created_timestamp: float


@dataclass(frozen=True)
class IntelligenceResult:
    signal_id: str
    status: IntelligenceStatus
    requested: bool
    annotation: IntelligenceAnnotation | None
    fallback_reason: FallbackReason
    model_calls: int
    router_latency_s: float | None = None
    model_latency_s: float | None = None
    parse_latency_s: float | None = None


@dataclass(frozen=True)
class EpisodeCallBudget:
    max_calls: int = 1
    allow_escalation_recall: bool = False


def budget_allows_call(
    budget: EpisodeCallBudget,
    *,
    calls_made: int,
    current: SignalPriority,
    last_priority: SignalPriority | None = None,
) -> bool:
    if calls_made < budget.max_calls:
        return True
    if not budget.allow_escalation_recall:
        return False
    if last_priority is None:
        return False
    if calls_made >= budget.max_calls + 1:
        return False
    return _PRIORITY_RANK[current] > _PRIORITY_RANK[last_priority]

from __future__ import annotations

from dataclasses import dataclass

from market_sentinel.domain.enums import EventType, FeedStatus, SignalPriority
from market_sentinel.intelligence.contract import (
    EpisodeCallBudget,
    FallbackReason,
    IntelligenceInput,
    budget_allows_call,
)

_PRIORITY_RANK = {
    SignalPriority.INFO: 1,
    SignalPriority.NOTICE: 2,
    SignalPriority.IMPORTANT: 3,
    SignalPriority.CRITICAL: 4,
}

_PRICE = frozenset({EventType.RAPID_MOVE.value, EventType.PRICE_VOLUME_EXPANSION.value})
_VOLUME = frozenset({EventType.VOLUME_SPIKE.value, EventType.PRICE_VOLUME_EXPANSION.value})
_BREAKOUT = frozenset({EventType.DAY_HIGH_BREAKOUT.value, EventType.DAY_LOW_BREAKDOWN.value})
_UNHEALTHY = frozenset({FeedStatus.STALE, FeedStatus.DISCONNECTED})


@dataclass(frozen=True)
class RouterPolicy:
    min_priority: SignalPriority = SignalPriority.IMPORTANT
    require_alert_edge: bool = True
    min_convergence_types: int = 3


@dataclass(frozen=True)
class RouterDecision:
    requested: bool
    reason: FallbackReason
    candidate: bool


def _is_candidate(row: IntelligenceInput, policy: RouterPolicy) -> bool:
    if _PRIORITY_RANK[row.priority] >= _PRIORITY_RANK[policy.min_priority]:
        return True
    types = set(row.event_types)
    price_volume_breakout = (
        bool(types & _PRICE) and bool(types & _VOLUME) and bool(types & _BREAKOUT)
    )
    if price_volume_breakout:
        return True
    return (
        len(types) >= policy.min_convergence_types
        and bool(types & _PRICE)
        and bool(types & _VOLUME)
    )


def _insufficient_features(row: IntelligenceInput) -> bool:
    return row.change_1m is None and row.change_5m is None and row.volume_ratio_5m is None


def need_intelligence(
    row: IntelligenceInput,
    *,
    policy: RouterPolicy | None = None,
    budget: EpisodeCallBudget | None = None,
) -> RouterDecision:
    policy = policy or RouterPolicy()
    budget = budget or EpisodeCallBudget()
    candidate = _is_candidate(row, policy)
    if row.expired:
        return RouterDecision(False, FallbackReason.EXPIRED_EPISODE, candidate)
    if policy.require_alert_edge and not row.alert_edge:
        return RouterDecision(False, FallbackReason.SUPPRESSED_EDGE, candidate)
    if row.feed_status in _UNHEALTHY:
        return RouterDecision(False, FallbackReason.STALE_FEED, candidate)
    if _insufficient_features(row):
        return RouterDecision(False, FallbackReason.INSUFFICIENT_FEATURES, candidate)
    if not candidate:
        return RouterDecision(False, FallbackReason.NOT_CANDIDATE, False)
    if not budget_allows_call(
        budget,
        calls_made=row.episode_call_count,
        current=row.priority,
        last_priority=row.last_requested_priority,
    ):
        return RouterDecision(False, FallbackReason.EPISODE_BUDGET, True)
    return RouterDecision(True, FallbackReason.NONE, True)

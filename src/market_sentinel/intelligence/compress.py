from __future__ import annotations

from typing import Any

from market_sentinel.domain.enums import FeedStatus, SignalPriority
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.intelligence.contract import IntelligenceInput

MODEL_PAYLOAD_KEYS = frozenset(
    {
        "signal_id",
        "symbol",
        "family",
        "direction",
        "priority",
        "event_types",
        "change_1m",
        "change_5m",
        "volume_ratio_5m",
        "above_vwap",
        "rsi14",
        "day_range_position",
    }
)

FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {
        "event_ids",
        "rule_names",
        "features",
        "priority_reason",
        "ticks",
        "snapshots",
        "ring_buffer",
        "source_code",
        "workspace",
        "conversation",
        "api_key",
        "prompt",
        "files",
    }
)


def compress_intelligence_input(
    *,
    signal: Signal,
    trace: SignalTrace,
    feed_status: FeedStatus,
    alert_edge: bool,
    episode_call_count: int,
    last_requested_priority: SignalPriority | None,
    expired: bool,
) -> IntelligenceInput:
    features = trace.features
    event_types = tuple(sorted(set(trace.rule_names)))
    return IntelligenceInput(
        signal_id=signal.id,
        symbol=signal.symbol,
        family=signal.family,
        direction=signal.direction,
        priority=signal.priority,
        event_types=event_types,
        change_1m=features.change_1m,
        change_5m=features.change_5m,
        volume_ratio_5m=features.volume_ratio_5m,
        above_vwap=features.above_vwap,
        rsi14=features.rsi14,
        day_range_position=features.day_range_position,
        feed_status=feed_status,
        alert_edge=alert_edge,
        episode_call_count=episode_call_count,
        last_requested_priority=last_requested_priority,
        expired=expired,
    )


def to_model_payload(row: IntelligenceInput) -> dict[str, Any]:
    return {
        "signal_id": row.signal_id,
        "symbol": row.symbol,
        "family": row.family,
        "direction": row.direction.value,
        "priority": row.priority.value,
        "event_types": list(row.event_types),
        "change_1m": row.change_1m,
        "change_5m": row.change_5m,
        "volume_ratio_5m": row.volume_ratio_5m,
        "above_vwap": row.above_vwap,
        "rsi14": row.rsi14,
        "day_range_position": row.day_range_position,
    }

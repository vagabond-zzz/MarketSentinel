from __future__ import annotations

import json

import pytest
from tests.unit.events.helpers import make_features

from market_sentinel.domain.enums import EventDirection, FeedStatus, GeneratedBy, SignalPriority
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.intelligence.compress import (
    FORBIDDEN_PAYLOAD_KEYS,
    MODEL_PAYLOAD_KEYS,
    compress_intelligence_input,
    to_model_payload,
)
from market_sentinel.intelligence.contract import (
    EpisodeCallBudget,
    FallbackReason,
    IntelligenceAnnotation,
    IntelligenceInput,
    IntelligenceResult,
    IntelligenceStatus,
    budget_allows_call,
)


def _signal(**overrides: object) -> Signal:
    payload = dict(
        id="sig-1",
        event_ids=("ev-1", "ev-2"),
        symbol="00700.HK",
        family="price_volume",
        direction=EventDirection.UP,
        priority=SignalPriority.IMPORTANT,
        title="headline",
        summary="rule summary",
        generated_by=GeneratedBy.RULE,
        market_timestamp=1_700_000_010.0,
        received_timestamp=1_700_000_011.0,
        detected_timestamp=1_700_000_012.0,
        signal_created_timestamp=1_700_000_012.0,
    )
    payload.update(overrides)
    return Signal(**payload)  # type: ignore[arg-type]


def test_signal_remains_rule_fact_without_intelligence_fields() -> None:
    signal = _signal()
    assert signal.generated_by is GeneratedBy.RULE
    assert signal.summary == "rule summary"
    assert not hasattr(signal, "intelligence")
    assert not hasattr(signal, "worth_highlight")


def test_intelligence_input_is_compressed_facts_not_trace() -> None:
    signal = _signal()
    features = make_features(
        change_1m=0.008,
        change_5m=0.018,
        volume_ratio_5m=2.6,
        above_vwap=True,
        rsi14=68.0,
        day_range_position=0.91,
    )
    trace = SignalTrace(
        signal_id=signal.id,
        event_ids=signal.event_ids,
        rule_names=("rapid_move", "volume_spike", "day_high_breakout"),
        features=features,
        family=signal.family,
        direction=signal.direction,
        priority=signal.priority,
        priority_reason="cluster",
        detected_timestamp=signal.detected_timestamp,
        signal_created_timestamp=signal.signal_created_timestamp,
    )
    row = compress_intelligence_input(
        signal=signal,
        trace=trace,
        feed_status=FeedStatus.LIVE,
        alert_edge=True,
        episode_call_count=0,
        last_requested_priority=None,
        expired=False,
    )
    assert isinstance(row, IntelligenceInput)
    assert row.signal_id == "sig-1"
    assert row.symbol == "00700.HK"
    assert row.family == "price_volume"
    assert row.direction == EventDirection.UP
    assert row.priority == SignalPriority.IMPORTANT
    assert row.event_types == ("day_high_breakout", "rapid_move", "volume_spike")
    assert row.change_1m == pytest.approx(0.008)
    assert row.change_5m == pytest.approx(0.018)
    assert row.volume_ratio_5m == pytest.approx(2.6)
    assert row.above_vwap is True
    assert row.rsi14 == pytest.approx(68.0)
    assert row.day_range_position == pytest.approx(0.91)
    assert row.feed_status is FeedStatus.LIVE
    assert row.alert_edge is True
    assert row.episode_call_count == 0
    payload = to_model_payload(row)
    assert set(payload) <= MODEL_PAYLOAD_KEYS
    assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(payload)
    blob = json.dumps(payload)
    assert "event_ids" not in blob
    assert "rule_names" not in blob
    assert "priority_reason" not in blob
    assert "RingBuffer" not in blob
    assert "DASHSCOPE" not in blob


def test_annotation_attaches_by_signal_id_without_replacing_summary() -> None:
    signal = _signal()
    annotation = IntelligenceAnnotation(
        signal_id=signal.id,
        worth_highlight=True,
        reason="price and volume expanded together",
        confidence=0.82,
        summary="Price-volume expansion is unusually strong.",
        created_timestamp=1_700_000_020.0,
    )
    result = IntelligenceResult(
        signal_id=signal.id,
        status=IntelligenceStatus.ENRICHED,
        requested=True,
        annotation=annotation,
        fallback_reason=FallbackReason.NONE,
        model_calls=1,
        router_latency_s=0.001,
        model_latency_s=0.2,
        parse_latency_s=0.001,
    )
    assert signal.summary == "rule summary"
    assert result.annotation is not None
    assert result.annotation.summary != signal.summary
    assert result.annotation.signal_id == signal.id


def test_episode_budget_defaults_to_one_call_and_denies_escalation() -> None:
    budget = EpisodeCallBudget()
    assert budget.max_calls == 1
    assert budget.allow_escalation_recall is False
    assert budget_allows_call(budget, calls_made=0, current=SignalPriority.IMPORTANT) is True
    assert budget_allows_call(budget, calls_made=1, current=SignalPriority.CRITICAL) is False
    open_budget = EpisodeCallBudget(max_calls=1, allow_escalation_recall=True)
    assert (
        budget_allows_call(
            open_budget,
            calls_made=1,
            current=SignalPriority.CRITICAL,
            last_priority=SignalPriority.IMPORTANT,
        )
        is True
    )
    assert (
        budget_allows_call(
            open_budget,
            calls_made=1,
            current=SignalPriority.IMPORTANT,
            last_priority=SignalPriority.IMPORTANT,
        )
        is False
    )

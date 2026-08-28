from __future__ import annotations

import logging

import pytest
from tests.unit.events.helpers import make_features

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import (
    EventDirection,
    FeedStatus,
    GeneratedBy,
    SchedulerLevel,
    SignalPriority,
)
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.intelligence.contract import (
    FallbackReason,
    IntelligenceStatus,
)
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.errors import (
    IntelligenceRateLimitError,
    IntelligenceTransportError,
)
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.view import intelligence_view
from market_sentinel.runtime.results import EngineTickResult, SymbolTickResult


def _signal() -> Signal:
    return Signal(
        id="sig-1",
        event_ids=("ev-1",),
        symbol="00700.HK",
        family="price_volume",
        direction=EventDirection.UP,
        priority=SignalPriority.IMPORTANT,
        title="headline",
        summary="rule summary",
        generated_by=GeneratedBy.RULE,
        market_timestamp=1.0,
        received_timestamp=1.0,
        detected_timestamp=1.0,
        signal_created_timestamp=1.0,
    )


def _tick(signal: Signal) -> EngineTickResult:
    features = make_features(
        change_1m=0.008,
        change_5m=0.018,
        volume_ratio_5m=2.6,
        above_vwap=True,
        rsi14=60.0,
        day_range_position=0.9,
    )
    trace = SignalTrace(
        signal_id=signal.id,
        event_ids=signal.event_ids,
        rule_names=("rapid_move", "volume_spike"),
        features=features,
        family=signal.family,
        direction=signal.direction,
        priority=signal.priority,
        priority_reason="cluster",
        detected_timestamp=signal.detected_timestamp,
        signal_created_timestamp=signal.signal_created_timestamp,
    )
    row = SymbolTickResult(
        symbol=signal.symbol,
        features=features,
        accepted_events=(),
        signal_updates=(signal,),
        traces=(trace,),
        alert_candidates=(signal,),
        level_before=SchedulerLevel.HOT,
        level_after=SchedulerLevel.HOT,
    )
    return EngineTickResult(symbol_results=(row,))


@pytest.mark.asyncio
async def test_missing_annotation_is_not_requested_and_does_not_replace_summary() -> None:
    signal = _signal()
    view = intelligence_view(None, signal.id)
    assert view.status is IntelligenceStatus.NOT_REQUESTED
    assert signal.summary == "rule summary"
    assert view.annotation is None


@pytest.mark.asyncio
async def test_status_reaches_enriched_and_records_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    model = FakeIntelligenceProvider(delay_s=0.05)
    clock = FakeClock()
    coordinator = IntelligenceCoordinator(model, clock, secrets=("sk-secret",))
    await coordinator.start()
    signal = _signal()
    coordinator.observe_tick(
        _tick(signal),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={signal.id},
    )
    queued = coordinator.registry.get(signal.id)
    assert queued is not None
    assert queued.status in {
        IntelligenceStatus.QUEUED,
        IntelligenceStatus.RUNNING,
        IntelligenceStatus.ENRICHED,
    }
    await coordinator.idle()
    enriched = coordinator.registry.get(signal.id)
    assert enriched is not None
    assert enriched.status is IntelligenceStatus.ENRICHED
    assert enriched.annotation is not None
    assert signal.summary == "rule summary"
    assert enriched.annotation.summary != signal.summary
    snap = coordinator.diagnostics.snapshot()
    assert snap["router_decisions"] == 1
    assert snap["requests_submitted"] == 1
    assert snap["model_calls"] == 1
    assert "sk-secret" not in caplog.text
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_rate_limit_fallback_is_visible_without_dropping_signal() -> None:
    model = FakeIntelligenceProvider(error=IntelligenceRateLimitError("rate"))
    clock = FakeClock()
    coordinator = IntelligenceCoordinator(model, clock)
    await coordinator.start()
    signal = _signal()
    coordinator.observe_tick(
        _tick(signal),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={signal.id},
    )
    await coordinator.idle()
    stored = coordinator.registry.get(signal.id)
    assert stored is not None
    assert stored.status is IntelligenceStatus.FALLBACK
    assert stored.fallback_reason is FallbackReason.RATE_LIMITED
    assert stored.annotation is None
    assert coordinator.diagnostics.rate_limit_count == 1
    assert coordinator.diagnostics.fallback_count == 1
    view = intelligence_view(stored, signal.id)
    assert view.status is IntelligenceStatus.FALLBACK
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_coordinator_redacts_secrets_in_fallback_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    model = FakeIntelligenceProvider(error=IntelligenceTransportError("failed sk-secret"))
    clock = FakeClock()
    coordinator = IntelligenceCoordinator(model, clock, secrets=("sk-secret",))
    await coordinator.start()
    signal = _signal()
    coordinator.observe_tick(
        _tick(signal),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={signal.id},
    )
    await coordinator.idle()
    assert "sk-secret" not in caplog.text
    assert "[redacted]" in caplog.text
    await coordinator.shutdown()

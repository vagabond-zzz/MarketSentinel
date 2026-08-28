from __future__ import annotations

import asyncio
from dataclasses import replace

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
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.parse import ModelCompletion
from market_sentinel.runtime.results import EngineTickResult, SymbolTickResult


def _signal(signal_id: str) -> Signal:
    return Signal(
        id=signal_id,
        event_ids=(f"ev-{signal_id}",),
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


def _tick(*signals: Signal) -> EngineTickResult:
    features = make_features(
        change_1m=0.008,
        change_5m=0.018,
        volume_ratio_5m=2.6,
        above_vwap=True,
        rsi14=60.0,
        day_range_position=0.9,
    )
    rows: list[SymbolTickResult] = []
    for signal in signals:
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
        rows.append(
            SymbolTickResult(
                symbol=signal.symbol,
                features=features,
                accepted_events=(),
                signal_updates=(signal,),
                traces=(trace,),
                alert_candidates=(signal,),
                level_before=SchedulerLevel.HOT,
                level_after=SchedulerLevel.HOT,
            )
        )
    return EngineTickResult(symbol_results=tuple(rows))


def _empty_tick() -> EngineTickResult:
    return EngineTickResult(symbol_results=())


class _GateProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[object] = []
        self.last_parse_latency_s = 0.0
        self.scripted = ModelCompletion(True, "scripted", 0.5, "scripted summary")

    async def complete(self, payload: object, *, timeout_s: float) -> ModelCompletion:
        del timeout_s
        self.calls.append(payload)
        self.started.set()
        await self.release.wait()
        return self.scripted


@pytest.mark.asyncio
async def test_queued_work_is_discarded_when_episode_becomes_inactive() -> None:
    model = FakeIntelligenceProvider()
    coordinator = IntelligenceCoordinator(model, FakeClock())
    await coordinator.start()
    first = _signal("sig-a")
    second = _signal("sig-b")
    coordinator.observe_tick(
        _tick(first, second),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={first.id, second.id},
    )
    assert coordinator.diagnostics.requests_submitted == 2
    coordinator.observe_tick(
        _empty_tick(),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids=set(),
    )
    await coordinator.idle()
    assert model.calls == []
    assert coordinator.diagnostics.model_calls == 0
    assert coordinator.diagnostics.stale_discard == 2
    assert coordinator.registry.get(first.id) is None
    assert coordinator.registry.get(second.id) is None
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_in_flight_completion_does_not_resurrect_retired_episode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _GateProvider()
    coordinator = IntelligenceCoordinator(model, FakeClock())
    monkeypatch.setattr(coordinator, "_cancel_in_flight", lambda _signal_id: None, raising=False)
    await coordinator.start()
    signal = _signal("sig-inflight")
    coordinator.observe_tick(
        _tick(signal),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={signal.id},
    )
    await asyncio.wait_for(model.started.wait(), timeout=2)
    assert model.calls
    coordinator.observe_tick(
        _empty_tick(),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids=set(),
    )
    assert coordinator.registry.get(signal.id) is None
    model.release.set()
    await coordinator.idle()
    assert coordinator.registry.get(signal.id) is None
    stored = coordinator.registry.get(signal.id)
    assert stored is None or stored.annotation is None
    assert coordinator.diagnostics.stale_discard >= 1
    assert coordinator.diagnostics.model_calls == 1
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_retired_episode_bookkeeping_is_bounded() -> None:
    model = FakeIntelligenceProvider()
    coordinator = IntelligenceCoordinator(model, FakeClock(), queue_size=8)
    await coordinator.start()
    for index in range(80):
        signal = _signal(f"sig-{index}")
        coordinator.observe_tick(
            _tick(signal),
            feed_status_for=lambda _symbol: FeedStatus.LIVE,
            active_ids={signal.id},
        )
        coordinator.observe_tick(
            _empty_tick(),
            feed_status_for=lambda _symbol: FeedStatus.LIVE,
            active_ids=set(),
        )
        await coordinator.idle()
    assert coordinator.tracked_episode_count() == 0
    assert coordinator.registry.get("sig-0") is None
    assert coordinator.registry.get("sig-79") is None
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_expires_at_marks_episode_expired_before_enqueue() -> None:
    model = FakeIntelligenceProvider()
    coordinator = IntelligenceCoordinator(model, FakeClock())
    await coordinator.start()
    signal = replace(_signal("sig-exp"), expires_at=1.0)
    coordinator.observe_tick(
        _tick(signal),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={signal.id},
    )
    assert coordinator.diagnostics.requests_submitted == 0
    assert model.calls == []
    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_shutdown_clears_queued_episode_state() -> None:
    model = FakeIntelligenceProvider()
    coordinator = IntelligenceCoordinator(model, FakeClock())
    await coordinator.start()
    signals = (_signal("s0"), _signal("s1"), _signal("s2"))
    coordinator.observe_tick(
        _tick(*signals),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={item.id for item in signals},
    )
    submitted = coordinator.diagnostics.requests_submitted
    assert submitted == 3
    assert coordinator.tracked_episode_count() == 3
    assert coordinator.registry.ids() == {"s0", "s1", "s2"}
    await coordinator.shutdown()
    assert coordinator.tracked_episode_count() == 0
    assert coordinator.registry.ids() == set()
    assert coordinator.diagnostics.requests_submitted == submitted
    assert model.calls == []


@pytest.mark.asyncio
async def test_coordinator_can_restart_cleanly_after_shutdown() -> None:
    model = FakeIntelligenceProvider()
    coordinator = IntelligenceCoordinator(model, FakeClock())
    await coordinator.start()
    first = _signal("s0")
    coordinator.observe_tick(
        _tick(first),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={first.id},
    )
    assert coordinator.diagnostics.requests_submitted == 1
    await coordinator.shutdown()
    assert coordinator.tracked_episode_count() == 0
    assert coordinator.registry.ids() == set()
    await coordinator.start()
    coordinator.observe_tick(
        _tick(first),
        feed_status_for=lambda _symbol: FeedStatus.LIVE,
        active_ids={first.id},
    )
    await coordinator.idle()
    assert coordinator.diagnostics.requests_submitted == 2
    assert len(model.calls) == 1
    stored = coordinator.registry.get(first.id)
    assert stored is not None
    await coordinator.shutdown()
    assert coordinator.tracked_episode_count() == 0
    assert coordinator.registry.ids() == set()

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.unit.intelligence.test_router import _input

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import FeedStatus, SignalPriority
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.compress import FORBIDDEN_PAYLOAD_KEYS, MODEL_PAYLOAD_KEYS
from market_sentinel.intelligence.contract import EpisodeCallBudget, FallbackReason
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.errors import (
    IntelligenceMalformedError,
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
)
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.router import need_intelligence
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _batches(name: str) -> list[list[dict]]:
    path = FIXTURES / name
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


async def _eval(
    tmp_path: Path,
    fixture_name: str,
    model: FakeIntelligenceProvider,
    *,
    budget: EpisodeCallBudget | None = None,
) -> tuple[MarketEngine, IntelligenceCoordinator, FakeIntelligenceProvider, FakeClock]:
    batches = _batches(fixture_name)
    start = float(batches[0][0]["market_timestamp"])
    clock = FakeClock(wall=start, monotonic=0.0)
    coordinator = IntelligenceCoordinator(model, clock, budget=budget)
    await coordinator.start()
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add("00700.HK")
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=ReplayProvider(FIXTURES / fixture_name, clock),
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(cold_interval_s=0.0, warm_interval_s=0.0, hot_interval_s=0.0),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        intelligence=coordinator,
    )
    for batch in batches:
        clock.set_wall(float(batch[0]["market_timestamp"]))
        await engine.tick()
    await coordinator.idle()
    return engine, coordinator, model, clock


@pytest.mark.integration
async def test_eval_normal_market_is_offline_fake_and_zero_model_calls(tmp_path: Path) -> None:
    """Offline FakeIntelligenceProvider evaluation — not a live LLM test."""
    model = FakeIntelligenceProvider()
    _, coordinator, model, _clock = await _eval(tmp_path, "normal_market.jsonl", model)
    snap = coordinator.diagnostics.snapshot()
    assert snap["model_calls"] == 0
    assert model.calls == []
    await coordinator.shutdown()


@pytest.mark.integration
async def test_eval_significant_episode_is_one_fake_call_with_private_payload(
    tmp_path: Path,
) -> None:
    """Offline FakeIntelligenceProvider evaluation — not a live LLM test."""
    model = FakeIntelligenceProvider()
    engine, coordinator, model, _clock = await _eval(tmp_path, "price_volume_breakout.jsonl", model)
    snap = coordinator.diagnostics.snapshot()
    assert snap["model_calls"] == 1
    assert len(model.calls) == 1
    payload = dict(model.calls[0])
    assert set(payload) <= MODEL_PAYLOAD_KEYS
    blob = json.dumps(payload)
    assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(payload)
    assert "source_code" not in blob
    assert "workspace" not in blob
    assert "conversation" not in blob
    assert "DASHSCOPE" not in blob
    state = engine.states.get("00700.HK")
    assert state is not None and state.active_signals
    signal_id = state.active_signals[0].id
    stored = coordinator.registry.get(signal_id)
    assert stored is not None
    assert stored.annotation is not None
    await coordinator.shutdown()


@pytest.mark.integration
async def test_eval_repeated_episode_does_not_burn_again(tmp_path: Path) -> None:
    model = FakeIntelligenceProvider()
    _engine, coordinator, model, _clock = await _eval(
        tmp_path, "price_volume_breakout.jsonl", model
    )
    assert coordinator.diagnostics.model_calls == 1
    assert coordinator.diagnostics.requests_submitted == 1
    await coordinator.shutdown()


@pytest.mark.integration
async def test_eval_escalation_policy_stays_deterministic() -> None:
    blocked = need_intelligence(
        _input(
            episode_call_count=1,
            priority=SignalPriority.CRITICAL,
            last_requested_priority=SignalPriority.IMPORTANT,
        )
    )
    allowed = need_intelligence(
        _input(
            episode_call_count=1,
            priority=SignalPriority.CRITICAL,
            last_requested_priority=SignalPriority.IMPORTANT,
        ),
        budget=EpisodeCallBudget(allow_escalation_recall=True),
    )
    assert blocked.requested is False
    assert allowed.requested is True


@pytest.mark.integration
@pytest.mark.parametrize(
    "error",
    [
        IntelligenceTimeoutError("timeout"),
        IntelligenceMalformedError("bad json"),
        IntelligenceRateLimitError("rate"),
    ],
)
async def test_eval_model_failure_keeps_rule_signal(tmp_path: Path, error: Exception) -> None:
    model = FakeIntelligenceProvider(error=error)
    engine, coordinator, _model, _clock = await _eval(
        tmp_path, "price_volume_breakout.jsonl", model
    )
    state = engine.states.get("00700.HK")
    assert state is not None and state.active_signals
    stored = coordinator.registry.get(state.active_signals[0].id)
    assert stored is not None
    assert stored.annotation is None
    assert stored.fallback_reason is not FallbackReason.NONE
    assert coordinator.diagnostics.fallback_count == 1
    await coordinator.shutdown()


@pytest.mark.integration
async def test_eval_stale_feed_does_not_call_model(tmp_path: Path) -> None:
    model = FakeIntelligenceProvider()
    engine, coordinator, model, clock = await _eval(tmp_path, "rapid_move.jsonl", model)
    before = coordinator.diagnostics.model_calls
    engine.provider = FakeProvider(clock)
    engine.provider.set_timeout(True)
    clock.advance_monotonic(30.0)
    await engine.tick()
    assert engine.health.status("00700.HK") is FeedStatus.STALE
    await engine.tick()
    await coordinator.idle()
    assert coordinator.diagnostics.model_calls == before
    await coordinator.shutdown()


@pytest.mark.integration
async def test_eval_slow_fake_model_lets_replay_finish(tmp_path: Path) -> None:
    model = FakeIntelligenceProvider(delay_s=0.05)
    engine, coordinator, model, _clock = await _eval(tmp_path, "price_volume_breakout.jsonl", model)
    assert engine.states.get("00700.HK") is not None
    assert coordinator.diagnostics.model_calls == 1
    await coordinator.shutdown()

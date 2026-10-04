"""Unit tests for the read-only capabilities facade.

The capabilities layer is the future MCP security boundary, so these tests
cover error semantics, read-only guarantees, and isolation — not just the
happy path.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from market_sentinel.capabilities import (
    CapabilityError,
    CapabilityErrorCode,
    MarketCapabilities,
    RecentEventsBuffer,
    map_exception,
)
from market_sentinel.clock import FakeClock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.contract import (
    FallbackReason,
    IntelligenceAnnotation,
    IntelligenceResult,
    IntelligenceStatus,
)
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.tuning.replay import scheduler_policy_for_replay
from market_sentinel.watchlist.watchlist import Watchlist

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"
UUID_HEX = re.compile(r"\b[0-9a-f]{32}\b")


def _fake_engine(*, symbols: tuple[str, ...] = ("600519.SH",)) -> MarketEngine:
    clock = FakeClock()
    telemetry = TelemetryRuntime(clock, InMemoryTelemetryCollector())
    watchlist = Watchlist(persist=False)
    for symbol in symbols:
        watchlist.add(symbol)
    return MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=FakeProvider(clock),
        scheduler=AdaptiveScheduler(clock, scheduler_policy_for_replay()),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        telemetry=telemetry,
    )


def _replay_engine(
    fixture: str = "multi_a_share_ui.jsonl", *, intelligence: bool = False
) -> tuple[MarketEngine, FakeClock, IntelligenceCoordinator | None, TelemetryRuntime]:
    path = FIXTURE_DIR / fixture
    clock = FakeClock()
    telemetry = TelemetryRuntime(clock, InMemoryTelemetryCollector())
    watchlist = Watchlist(persist=False)
    quotes = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    symbols = list(dict.fromkeys(str(quote["symbol"]) for quote in quotes))
    for symbol in symbols:
        watchlist.add(symbol)
    provider = ReplayProvider(path, clock)
    coordinator: IntelligenceCoordinator | None = None
    if intelligence:
        coordinator = IntelligenceCoordinator(
            FakeIntelligenceProvider(), clock, timeout_s=8.0, telemetry=telemetry
        )
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock, scheduler_policy_for_replay()),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        intelligence=coordinator,
        telemetry=telemetry,
    )
    return engine, clock, coordinator, telemetry


async def _drive_replay(
    engine: MarketEngine,
    clock: FakeClock,
    capabilities: MarketCapabilities,
    coordinator: IntelligenceCoordinator | None,
    telemetry: TelemetryRuntime,
    fixture: str = "multi_a_share_ui.jsonl",
) -> None:
    path = FIXTURE_DIR / fixture
    if coordinator is not None:
        await coordinator.start()
    prev_ts: float | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            ts = float(json.loads(line)[0]["market_timestamp"])
            if prev_ts is not None:
                clock.advance_monotonic(max(0.0, ts - prev_ts))
            clock.set_wall(ts)
            prev_ts = ts
            result = await engine.tick()
            capabilities.observe_tick(result)
            await asyncio.sleep(0)
        if coordinator is not None:
            await coordinator.idle()
    finally:
        if coordinator is not None:
            await coordinator.shutdown()
        telemetry.close()


# ---------------------------------------------------------------- market state


async def test_market_state_after_tick() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    state = capabilities.get_market_state()
    assert state.watchlist_count == 1
    assert state.symbols[0].symbol == "600519.SH"
    assert state.symbols[0].price is not None
    assert state.symbols[0].feed_status == "LIVE"
    assert state.replay_complete is False


async def test_market_state_output_is_frozen() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    state = capabilities.get_market_state()
    with pytest.raises(FrozenInstanceError):
        state.watchlist_count = 99  # type: ignore[misc]


async def test_market_state_before_any_tick_is_coherent() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    state = capabilities.get_market_state()
    assert state.watchlist_count == 1
    assert state.symbols[0].price is None
    assert state.symbols[0].scheduler_level == "COLD"


# ---------------------------------------------------------------- symbol state


async def test_symbol_state_returns_snapshot() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    symbol_state = capabilities.get_symbol_state("600519.SH")
    assert symbol_state.symbol == "600519.SH"
    assert symbol_state.price is not None
    assert symbol_state.feed_status == "LIVE"


async def test_symbol_state_invalid_format_is_invalid_argument() -> None:
    capabilities = MarketCapabilities(_fake_engine())
    for bad in ("600519", "NOPE.XX", "600519.sh", 123):
        with pytest.raises(CapabilityError) as excinfo:
            capabilities.get_symbol_state(bad)  # type: ignore[arg-type]
        assert excinfo.value.code is CapabilityErrorCode.INVALID_ARGUMENT


async def test_symbol_state_unknown_symbol_is_not_found() -> None:
    capabilities = MarketCapabilities(_fake_engine())
    with pytest.raises(CapabilityError) as excinfo:
        capabilities.get_symbol_state("00700.HK")
    assert excinfo.value.code is CapabilityErrorCode.NOT_FOUND


# ------------------------------------------------------------- active signals


async def test_active_signals_empty_before_signals_exist() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    assert capabilities.get_active_signals() == {}


async def test_active_signals_grouped_by_symbol() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    active = capabilities.get_active_signals()
    assert active, "fixture should leave at least one active episode"
    for symbol, signals in active.items():
        assert symbol
        assert signals
        assert all(signal.id for signal in signals)


async def test_active_signals_returns_fresh_containers() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    first = capabilities.get_active_signals()
    first.clear()
    second = capabilities.get_active_signals()
    assert second, "caller mutation must not affect subsequent reads"


# ------------------------------------------------------------------- get_signal


async def test_get_signal_returns_wire_signal() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    active = capabilities.get_active_signals()
    symbol, signals = next(iter(active.items()))
    signal = capabilities.get_signal(signals[0].id)
    assert signal.id == signals[0].id
    assert signal.family
    assert signal.priority in {"info", "notice", "important", "critical"}


async def test_get_signal_not_found() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    with pytest.raises(CapabilityError) as excinfo:
        capabilities.get_signal("deadbeef" * 4)
    assert excinfo.value.code is CapabilityErrorCode.NOT_FOUND


async def test_get_signal_rejects_empty_id() -> None:
    capabilities = MarketCapabilities(_fake_engine())
    with pytest.raises(CapabilityError) as excinfo:
        capabilities.get_signal("   ")
    assert excinfo.value.code is CapabilityErrorCode.INVALID_ARGUMENT


async def test_get_signal_includes_intelligence_annotation() -> None:
    engine, clock, coordinator, telemetry = _replay_engine(intelligence=True)
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    active = capabilities.get_active_signals()
    assert active
    _symbol, signals = next(iter(active.items()))
    # Routed signals in this fixture expire before the final tick, so the
    # end-to-end path alone cannot guarantee an overlapping annotation.
    # Simulate a completed model call for a signal that is still active and
    # verify the capability surfaces it through the wire mapping.
    assert coordinator is not None
    coordinator.registry.put(
        IntelligenceResult(
            signal_id=signals[0].id,
            status=IntelligenceStatus.ENRICHED,
            requested=True,
            annotation=IntelligenceAnnotation(
                signal_id=signals[0].id,
                worth_highlight=True,
                reason="scripted",
                confidence=0.5,
                summary="scripted summary",
                created_timestamp=clock.wall_time(),
            ),
            fallback_reason=FallbackReason.NONE,
            model_calls=1,
        )
    )
    wire = capabilities.get_signal(signals[0].id)
    assert wire.intelligence is not None
    assert wire.intelligence.status == "enriched"
    assert wire.intelligence.summary == "scripted summary"


async def test_get_signal_without_intelligence_has_none() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    for signals in capabilities.get_active_signals().values():
        for signal in signals:
            assert signal.intelligence is None


# ---------------------------------------------------------------- feed health


async def test_feed_health_after_tick_is_live() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    report = capabilities.get_feed_health()
    assert report.aggregate_status == "LIVE"
    assert report.symbols[0].symbol == "600519.SH"
    assert report.symbols[0].status == "LIVE"


async def test_feed_health_ages_to_stale_without_ticks() -> None:
    engine, clock, _coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, None, telemetry)
    clock.advance_monotonic(40.0)  # stale_s=30 < 40s < disconnect_s=60
    report = capabilities.get_feed_health()
    assert report.aggregate_status == "STALE"


async def test_feed_health_does_not_touch_log_bookkeeping() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    for record in engine.health._symbols.values():  # noqa: SLF001 (test-only introspection)
        record.last_status = None
    capabilities.get_feed_health()
    for record in engine.health._symbols.values():  # noqa: SLF001
        assert record.last_status is None, "reads must not mutate tracker bookkeeping"


async def test_empty_watchlist_aggregates_to_disconnected() -> None:
    clock = FakeClock()
    telemetry = TelemetryRuntime(clock, InMemoryTelemetryCollector())
    engine = MarketEngine(
        clock=clock,
        watchlist=Watchlist(persist=False),
        provider=FakeProvider(clock),
        scheduler=AdaptiveScheduler(clock, scheduler_policy_for_replay()),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        telemetry=telemetry,
    )
    report = MarketCapabilities(engine).get_feed_health()
    assert report.aggregate_status == "DISCONNECTED"
    assert report.symbols == ()


# --------------------------------------------------------------- recent events


async def test_recent_events_empty_without_observed_ticks() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine)
    await engine.tick()
    assert capabilities.get_recent_events() == ()


async def test_recent_events_after_observed_ticks() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    events = capabilities.get_recent_events()
    assert events
    event = events[-1]
    assert event.symbol.startswith(("6005", "0000", "3007"))
    assert event.event_type
    assert event.severity >= 1
    assert event.rule_name
    with pytest.raises(FrozenInstanceError):
        event.severity = 0  # type: ignore[misc]


async def test_recent_events_limit_and_ordering() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    events = capabilities.get_recent_events(limit=2)
    assert len(events) == 2
    assert events[0].market_timestamp <= events[1].market_timestamp


async def test_recent_events_symbol_filter() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    events = capabilities.get_recent_events(symbol="000001.SZ")
    assert events
    assert all(event.symbol == "000001.SZ" for event in events)


async def test_recent_events_invalid_arguments() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    bad_limits = (
        {"limit": 0},
        {"limit": -1},
        {"limit": MarketCapabilities.MAX_RECENT_EVENTS + 1},
        {"limit": True},
    )
    for kwargs in bad_limits:
        with pytest.raises(CapabilityError) as excinfo:
            capabilities.get_recent_events(**kwargs)
        assert excinfo.value.code is CapabilityErrorCode.INVALID_ARGUMENT
    with pytest.raises(CapabilityError) as excinfo:
        capabilities.get_recent_events(symbol="not-a-symbol")
    assert excinfo.value.code is CapabilityErrorCode.INVALID_ARGUMENT


async def test_recent_events_buffer_is_bounded() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    buffer = RecentEventsBuffer(maxlen=5)
    capabilities = MarketCapabilities(engine, events=buffer)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    assert len(buffer) == 5


def test_recent_events_buffer_rejects_bad_maxlen() -> None:
    with pytest.raises(ValueError):
        RecentEventsBuffer(maxlen=0)


# ------------------------------------------------------------------ lifecycle


async def test_not_running_gate_blocks_all_capabilities() -> None:
    engine, clock, coordinator, telemetry = _replay_engine()
    capabilities = MarketCapabilities(engine, started=lambda: False)
    with pytest.raises(CapabilityError) as excinfo:
        capabilities.get_market_state()
    assert excinfo.value.code is CapabilityErrorCode.NOT_RUNNING
    with pytest.raises(CapabilityError):
        capabilities.get_symbol_state("600519.SH")
    with pytest.raises(CapabilityError):
        capabilities.get_active_signals()
    with pytest.raises(CapabilityError):
        capabilities.get_signal("x")
    with pytest.raises(CapabilityError):
        capabilities.get_feed_health()
    with pytest.raises(CapabilityError):
        capabilities.get_recent_events()
    del clock, coordinator, telemetry


async def test_started_gate_allows_reads_when_true() -> None:
    engine = _fake_engine()
    capabilities = MarketCapabilities(engine, started=lambda: True)
    assert capabilities.get_market_state().watchlist_count == 1


# ---------------------------------------------------------------- isolation


async def test_capability_reads_do_not_change_core_state() -> None:
    engine, clock, coordinator, telemetry = _replay_engine(intelligence=True)
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)

    symbols = ("600519.SH", "000001.SZ", "300750.SZ")

    def core_snapshot() -> object:
        return (
            {symbol: engine.states.get(symbol) for symbol in symbols},
            {symbol: engine.health.peek_status(symbol) for symbol in symbols},
            engine.watchlist.list(),
            tuple(engine.scheduler.get_level(symbol) for symbol in symbols),
        )

    before = core_snapshot()
    capabilities.get_market_state()
    capabilities.get_symbol_state("600519.SH")
    capabilities.get_active_signals()
    capabilities.get_feed_health()
    capabilities.get_recent_events()
    active = capabilities.get_active_signals()
    for signals in active.values():
        for signal in signals:
            capabilities.get_signal(signal.id)
    assert core_snapshot() == before


async def test_outputs_leak_no_secrets() -> None:
    engine, clock, coordinator, telemetry = _replay_engine(intelligence=True)
    capabilities = MarketCapabilities(engine)
    await _drive_replay(engine, clock, capabilities, coordinator, telemetry)
    payload = json.dumps(
        [
            capabilities.get_market_state().to_wire(),
            {s: [x.to_wire() for x in v] for s, v in capabilities.get_active_signals().items()},
            capabilities.get_feed_health().to_wire(),
            [event.to_wire() for event in capabilities.get_recent_events()],
        ],
        ensure_ascii=False,
    )
    for forbidden in ("LONGBRIDGE", "APP_SECRET", "ACCESS_TOKEN", "DASHSCOPE", "sk-", "api_key"):
        assert forbidden.lower() not in payload.lower(), forbidden


async def test_error_messages_leak_no_paths() -> None:
    capabilities = MarketCapabilities(_fake_engine())
    with pytest.raises(CapabilityError) as excinfo:
        capabilities.get_symbol_state("BAD_SYMBOL")
    assert "\\" not in str(excinfo.value)
    assert "/" not in str(excinfo.value)


# ---------------------------------------------------------------- error mapping


def test_map_exception_passthrough() -> None:
    original = CapabilityError(CapabilityErrorCode.UNAVAILABLE, "down")
    assert map_exception(original) is original


def test_map_exception_timeout() -> None:
    assert map_exception(TimeoutError()).code is CapabilityErrorCode.TIMEOUT


def test_map_exception_argument_types() -> None:
    assert map_exception(ValueError("x")).code is CapabilityErrorCode.INVALID_ARGUMENT
    assert map_exception(TypeError("x")).code is CapabilityErrorCode.INVALID_ARGUMENT


def test_map_exception_not_found_types() -> None:
    assert map_exception(KeyError("x")).code is CapabilityErrorCode.NOT_FOUND


def test_map_exception_unknown_is_internal() -> None:
    assert map_exception(RuntimeError("boom")).code is CapabilityErrorCode.INTERNAL


def test_error_code_values_are_stable() -> None:
    assert CapabilityErrorCode.NOT_FOUND.value == "not_found"
    assert CapabilityErrorCode.INVALID_ARGUMENT.value == "invalid_argument"
    assert CapabilityErrorCode.NOT_RUNNING.value == "not_running"
    assert CapabilityErrorCode.UNAVAILABLE.value == "unavailable"
    assert CapabilityErrorCode.TIMEOUT.value == "timeout"
    assert CapabilityErrorCode.INTERNAL.value == "internal"

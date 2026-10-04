"""`market-sentinel demo` — deterministic, offline walkthrough of the full chain.

Runs the real MarketEngine over a bundled replay fixture (fake clock, fake
intelligence provider, in-memory telemetry), publishes every finished tick to
the capabilities layer, and prints what each stage produced. No API keys, no
network, no files written, no production defaults changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from market_sentinel.capabilities import MarketCapabilities
from market_sentinel.clock import FakeClock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.tuning.replay import scheduler_policy_for_replay
from market_sentinel.watchlist.watchlist import Watchlist

DEFAULT_FIXTURE = Path("tests/fixtures/multi_a_share_ui.jsonl")


def register_demo(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "demo",
        help="deterministic offline walkthrough: provider→features→events→signals→capabilities",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="replay JSONL fixture (default: the bundled multi-symbol A-share scenario)",
    )


async def run_demo(args: argparse.Namespace) -> int:
    fixture = args.fixture if args.fixture is not None else _default_fixture()
    if fixture is None or not fixture.is_file():
        print(
            "demo fixture not found; run from a repository checkout or pass --fixture <path>",
            file=sys.stderr,
        )
        return 2
    return await _run(fixture)


def _default_fixture() -> Path | None:
    candidate = Path(__file__).resolve().parents[3] / DEFAULT_FIXTURE
    return candidate if candidate.is_file() else None


async def _run(fixture: Path) -> int:
    try:
        timestamps, symbols = _fixture_plan(fixture)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"cannot read fixture {fixture}: {exc}", file=sys.stderr)
        return 2
    if not symbols:
        print("fixture has no quotes on its first line", file=sys.stderr)
        return 2

    clock = FakeClock()
    collector = InMemoryTelemetryCollector()
    telemetry = TelemetryRuntime(clock, collector)
    watchlist = Watchlist(persist=False)
    for symbol in symbols:
        watchlist.add(symbol)
    provider = ReplayProvider(fixture, clock)
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
    capabilities = MarketCapabilities(engine)

    await coordinator.start()
    ticks = 0
    quotes = 0
    first_event: str | None = None
    first_alert: str | None = None
    prev_ts: float | None = None
    try:
        for ts in timestamps:
            if prev_ts is not None:
                clock.advance_monotonic(max(0.0, ts - prev_ts))
            clock.set_wall(ts)
            prev_ts = ts
            result = await engine.tick()
            capabilities.observe_tick(result)
            ticks += 1
            quotes += len(result.symbol_results)
            if first_event is None:
                for item in result.symbol_results:
                    if item.accepted_events:
                        event = item.accepted_events[0]
                        first_event = (
                            f"tick {ticks}: {event.type.value}({event.direction.value}) "
                            f"on {event.symbol}"
                        )
                        break
            if first_alert is None:
                for item in result.symbol_results:
                    if item.alert_candidates:
                        signal = item.alert_candidates[0]
                        first_alert = (
                            f"tick {ticks}: {signal.family}({signal.direction.value}) "
                            f"on {signal.symbol}"
                        )
                        break
            # yield so the intelligence worker drains between ticks
            await asyncio.sleep(0)
        await coordinator.idle()
    finally:
        await coordinator.shutdown()
        telemetry.close()

    counts = Counter(_telemetry_name(event) for event in collector.events)

    print("Market Sentinel demo — deterministic replay walkthrough")
    print(f"provider: replay ({fixture.name}) | intelligence: fake provider (no API key)")
    print(f"watchlist: {', '.join(symbols)}")
    print()
    print("[pipeline]")
    print(f"  replay batches ticked : {ticks}")
    print(f"  quotes processed      : {quotes}")
    generated = counts.get("event_generated", 0)
    deduped = counts.get("event_deduped", 0)
    print(
        f"  events accepted       : {generated - deduped}"
        f" ({generated} generated, {deduped} deduped)"
    )
    print(f"  signal episodes       : {counts.get('signal_episode_created', 0)}")
    print(
        f"  alert candidates      : {counts.get('alert_candidate', 0)}"
        f" ({counts.get('alert_suppressed', 0)} suppressed by cooldown)"
    )
    print(
        f"  intelligence calls    : {counts.get('intelligence_succeeded', 0)} succeeded"
        f" of {counts.get('intelligence_routed', 0)} routed"
    )
    if first_event is not None:
        print(f"  first event           : {first_event}")
    if first_alert is not None:
        print(f"  first alert candidate : {first_alert}")
    print()

    _print_capability("get_market_state()", _market_state_summary(capabilities))
    _print_capability("get_feed_health()", capabilities.get_feed_health().to_wire())
    active = capabilities.get_active_signals()
    _print_capability(
        "get_active_signals()",
        {symbol: [signal.to_wire() for signal in signals] for symbol, signals in active.items()},
    )
    first_id = next((signals[0].id for signals in active.values() if signals), None)
    if first_id is not None:
        _print_capability(f'get_signal("{first_id}")', capabilities.get_signal(first_id).to_wire())
    else:
        print('capability get_signal("<id>"): no active signal in this fixture')
    _print_capability(
        "get_recent_events(limit=3)",
        [item.to_wire() for item in capabilities.get_recent_events(limit=3)],
    )
    print()
    print("demo complete — no API keys, no network, no files written.")
    return 0


def _fixture_plan(fixture: Path) -> tuple[list[float], tuple[str, ...]]:
    timestamps: list[float] = []
    symbols: dict[str, None] = {}
    for line in fixture.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        quotes = json.loads(line)
        timestamps.append(float(quotes[0]["market_timestamp"]))
        for quote in quotes:
            symbols.setdefault(str(quote["symbol"]), None)
    return timestamps, tuple(symbols)


def _telemetry_name(event: object) -> str:
    name = getattr(event, "name", None)
    return str(getattr(name, "value", name))


def _market_state_summary(capabilities: MarketCapabilities) -> dict[str, object]:
    state = capabilities.get_market_state()
    return {
        "watchlist_count": state.watchlist_count,
        "feed_status": state.feed_status,
        "replay_complete": state.replay_complete,
        "symbols": [
            {
                "symbol": item.symbol,
                "price": item.price,
                "change_day": item.change_day,
                "scheduler_level": item.scheduler_level,
                "feed_status": item.feed_status,
            }
            for item in state.symbols
        ],
    }


def _print_capability(label: str, payload: object) -> None:
    print(f"capability {label}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()

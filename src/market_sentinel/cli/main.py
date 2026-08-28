from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from market_sentinel.cli.display import format_dashboard, format_updated
from market_sentinel.clock import SystemClock
from market_sentinel.errors import ProviderError
from market_sentinel.evaluation.aggregate import evaluate
from market_sentinel.evaluation.reader import TelemetryReader
from market_sentinel.evaluation.render import render_text
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.bootstrap import optional_intelligence
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.ipc.daemon import MarketDaemon
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.factory import create_provider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.telemetry.factory import jsonl_telemetry_runtime
from market_sentinel.telemetry.paths import resolve_data_dir, telemetry_jsonl_path
from market_sentinel.watchlist.watchlist import Watchlist


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )
    if args.command == "daemon":
        return asyncio.run(_handle_daemon(args))
    if args.command == "telemetry":
        return _handle_telemetry(args)
    watchlist = Watchlist(args.watchlist)

    if args.command == "watchlist":
        return _handle_watchlist(watchlist, args)
    if args.command == "run":
        return asyncio.run(_handle_run(watchlist, args))
    parser.error(f"unknown command: {args.command}")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="market-sentinel")
    parser.add_argument(
        "--watchlist",
        type=Path,
        default=Path("data/watchlist.json"),
        help="JSON watchlist path",
    )
    parser.add_argument(
        "--provider",
        choices=("fake", "replay", "longbridge", "http"),
        default="fake",
    )
    parser.add_argument(
        "--replay", type=Path, default=None, help="JSONL fixture for replay provider"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run diagnostics")
    run.add_argument("--once", action="store_true", help="run a single tick and exit")
    run.add_argument(
        "--verbose",
        action="store_true",
        help="show tick diagnostics (ids, timestamps, scheduler transition)",
    )
    watchlist = sub.add_parser("watchlist", help="manage watched symbols")
    watch_sub = watchlist.add_subparsers(dest="watchlist_command", required=True)
    add = watch_sub.add_parser("add")
    add.add_argument("symbol")
    remove = watch_sub.add_parser("remove")
    remove.add_argument("symbol")
    watch_sub.add_parser("list")
    enable = watch_sub.add_parser("enable")
    enable.add_argument("symbol")
    disable = watch_sub.add_parser("disable")
    disable.add_argument("symbol")
    sub.add_parser("daemon", help="JSONL stdio host protocol")
    telemetry = sub.add_parser("telemetry", help="read-only telemetry evaluation")
    tel_sub = telemetry.add_subparsers(dest="telemetry_command", required=True)
    report = tel_sub.add_parser("report", help="evaluation report from local JSONL")
    report.add_argument("--data-dir", type=Path, default=None)
    report.add_argument("--run-id", default=None)
    report.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def _handle_watchlist(watchlist: Watchlist, args: argparse.Namespace) -> int:
    command = args.watchlist_command
    if command == "add":
        watchlist.add(args.symbol)
    elif command == "remove":
        watchlist.remove(args.symbol)
    elif command == "enable":
        watchlist.enable(args.symbol)
    elif command == "disable":
        watchlist.disable(args.symbol)
    elif command == "list":
        pass
    else:
        return 2
    for item in watchlist.list():
        flag = "on" if item.enabled else "off"
        print(f"{item.symbol} {flag}")
    return 0


@asynccontextmanager
async def _intelligence_lifecycle(
    intelligence: IntelligenceCoordinator | None,
) -> AsyncIterator[None]:
    if intelligence is None:
        yield
        return
    await intelligence.start()
    try:
        yield
    finally:
        await intelligence.shutdown()


async def _handle_daemon(args: argparse.Namespace) -> int:
    clock = SystemClock()
    try:
        provider = create_provider(args.provider, clock, replay_path=args.replay)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    telemetry = jsonl_telemetry_runtime(clock)
    intelligence = optional_intelligence(clock, telemetry=telemetry)
    engine = MarketEngine(
        clock=clock,
        watchlist=Watchlist(persist=False),
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        intelligence=intelligence,
        telemetry=telemetry,
    )
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    return await MarketDaemon(engine, stdin=sys.stdin, stdout=sys.stdout).run()


async def _handle_run(watchlist: Watchlist, args: argparse.Namespace) -> int:
    clock = SystemClock()
    try:
        provider = create_provider(args.provider, clock, replay_path=args.replay)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ProviderError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    telemetry = jsonl_telemetry_runtime(clock)
    intelligence = optional_intelligence(clock, telemetry=telemetry)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        intelligence=intelligence,
        telemetry=telemetry,
    )
    async with _intelligence_lifecycle(intelligence):
        try:
            if args.once:
                result = await engine.tick()
                if intelligence is not None:
                    await intelligence.idle()
                _print_dashboard(engine, result, verbose=args.verbose)
                return 0
            try:
                while True:
                    result = await engine.tick()
                    _print_dashboard(engine, result, verbose=args.verbose)
                    await asyncio.sleep(
                        engine.scheduler.next_wait_s(engine.watchlist.enabled_symbols())
                    )
            except KeyboardInterrupt:
                return 0
        finally:
            engine.telemetry.close()
    return 0


def _handle_telemetry(args: argparse.Namespace) -> int:
    if args.telemetry_command != "report":
        return 2
    data_dir = resolve_data_dir(args.data_dir)
    loaded = TelemetryReader().load(telemetry_jsonl_path(data_dir))
    report = evaluate(loaded, run_id=args.run_id)
    record = report.to_record()
    if args.format == "text":
        print(render_text(report), end="")
    else:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


def _print_dashboard(
    engine: MarketEngine,
    tick_result: EngineTickResult,
    *,
    verbose: bool,
) -> None:
    symbols = engine.watchlist.enabled_symbols() or [
        item.symbol for item in engine.watchlist.list()
    ]
    states = engine.states.snapshot_for(symbols)
    feed = (
        engine.health.aggregate_status(symbols) if symbols else engine.health.aggregate_status([])
    )
    print(
        format_dashboard(
            feed,
            states,
            watchlist_count=len(engine.watchlist.list()),
            tick_result=tick_result,
            updated=format_updated(engine.clock.wall_time()),
            verbose=verbose,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

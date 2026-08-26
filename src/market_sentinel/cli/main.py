from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from market_sentinel.cli.display import format_dashboard
from market_sentinel.clock import SystemClock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
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
        choices=("fake", "replay", "http"),
        default="fake",
    )
    parser.add_argument(
        "--replay", type=Path, default=None, help="JSONL fixture for replay provider"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run diagnostics")
    run.add_argument("--once", action="store_true", help="run a single tick and exit")
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


async def _handle_run(watchlist: Watchlist, args: argparse.Namespace) -> int:
    if args.provider == "http":
        print(
            "HttpQuoteProvider is not required for v0.1 Core; use fake or replay.", file=sys.stderr
        )
        return 2
    clock = SystemClock()
    provider: FakeProvider | ReplayProvider
    if args.provider == "replay":
        if args.replay is None:
            print("--replay path is required for replay provider", file=sys.stderr)
            return 2
        provider = ReplayProvider(args.replay, clock)
    else:
        provider = FakeProvider(clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    if args.once:
        await engine.tick()
        _print_dashboard(engine)
        return 0
    try:
        while True:
            await engine.tick()
            _print_dashboard(engine)
            await asyncio.sleep(engine.scheduler.next_wait_s(engine.watchlist.enabled_symbols()))
    except KeyboardInterrupt:
        return 0
    return 0


def _print_dashboard(engine: MarketEngine) -> None:
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
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

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
from market_sentinel.errors import ProviderError, TuningConfigError, TuningSnapshotError
from market_sentinel.evaluation.aggregate import evaluate
from market_sentinel.evaluation.reader import LoadedTelemetry, TelemetryReader
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
from market_sentinel.telemetry.contract import TuningSource
from market_sentinel.telemetry.factory import jsonl_telemetry_runtime
from market_sentinel.telemetry.paths import (
    feedback_jsonl_path,
    resolve_data_dir,
    telemetry_jsonl_path,
)
from market_sentinel.tuning.compare import compare_artifacts, empty_feedback_dataset
from market_sentinel.tuning.config import OfflineTuningConfig, capture_baseline_config
from market_sentinel.tuning.feedback import build_tuning_feedback_dataset
from market_sentinel.tuning.replay import DEFAULT_CORPUS, default_fixture_dir, validate_corpus
from market_sentinel.tuning.store import load_snapshot, make_artifact, write_snapshot
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
    if args.command == "tuning":
        return _handle_tuning(args)
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
    tuning = sub.add_parser("tuning", help="offline snapshot and replay comparison")
    tun_sub = tuning.add_subparsers(dest="tuning_command", required=True)
    snap = tun_sub.add_parser("snapshot", help="write an immutable offline tuning snapshot")
    snap.add_argument("--config-version", required=True)
    snap.add_argument("--source", choices=("manual", "offline_eval"), default="offline_eval")
    snap.add_argument("--config", type=Path, default=None, help="OfflineTuningConfig JSON object")
    snap.add_argument("--data-dir", type=Path, default=None)
    compare = tun_sub.add_parser("compare", help="replay baseline vs candidate on a fixed corpus")
    _add_tuning_compare_args(compare)
    report_cmd = tun_sub.add_parser("report", help="same as compare; prints a fact report")
    _add_tuning_compare_args(report_cmd)
    return parser


def _add_tuning_compare_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--baseline", required=True, help="baseline snapshot_id")
    parser.add_argument("--candidate", required=True, help="candidate snapshot_id")
    parser.add_argument("--corpus", default="default", help="default or comma-separated corpus ids")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--fixture-dir", type=Path, default=None)


def _empty_loaded() -> LoadedTelemetry:
    return LoadedTelemetry((), (), 0, 0, False, True)


def _handle_tuning(args: argparse.Namespace) -> int:
    command = args.tuning_command
    if command in {"compare", "report"}:
        return asyncio.run(_handle_tuning_compare(args))
    if command != "snapshot":
        return 2
    try:
        data_dir = resolve_data_dir(args.data_dir)
        if args.config is None:
            config = capture_baseline_config()
        else:
            payload = json.loads(args.config.read_text(encoding="utf-8"))
            config = OfflineTuningConfig.from_record(payload)
        artifact = make_artifact(
            config,
            config_version=args.config_version,
            source=TuningSource(args.source),
        )
        path = write_snapshot(data_dir, artifact)
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TuningConfigError,
        TuningSnapshotError,
        ValueError,
    ):
        logging.getLogger(__name__).exception("tuning snapshot failed")
        return 2
    print(
        json.dumps(
            {
                "snapshot_id": artifact.snapshot.snapshot_id,
                "config_version": artifact.snapshot.config_version,
                "path_name": path.name,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _optional_tuning_feedback(data_dir: Path):
    tel = telemetry_jsonl_path(data_dir)
    fb = feedback_jsonl_path(data_dir)
    if not tel.is_file() and not fb.is_file():
        return empty_feedback_dataset()
    reader = TelemetryReader()
    telemetry = reader.load(tel) if tel.is_file() else _empty_loaded()
    feedback = reader.load(fb) if fb.is_file() else _empty_loaded()
    return build_tuning_feedback_dataset(feedback.records, telemetry.records)


async def _handle_tuning_compare(args: argparse.Namespace) -> int:
    try:
        data_dir = resolve_data_dir(args.data_dir)
        baseline = load_snapshot(data_dir, args.baseline)
        candidate = load_snapshot(data_dir, args.candidate)
        fixture_dir = args.fixture_dir if args.fixture_dir is not None else default_fixture_dir()
        work_dir = data_dir / "tuning-work"
        work_dir.mkdir(parents=True, exist_ok=True)
        report = await compare_artifacts(
            baseline,
            candidate,
            corpus=_parse_corpus(args.corpus),
            fixture_dir=fixture_dir,
            work_dir=work_dir,
            feedback=_optional_tuning_feedback(data_dir),
        )
    except (TuningConfigError, TuningSnapshotError, OSError, ValueError):
        logging.getLogger(__name__).exception("tuning compare failed")
        return 2
    print(json.dumps(report.to_record(), ensure_ascii=False, indent=2))
    return 0


def _parse_corpus(raw: str) -> tuple[str, ...]:
    if raw.strip() == "" or raw.strip() == "default":
        return DEFAULT_CORPUS
    parts = tuple(part.strip() for part in raw.split(",") if part.strip())
    return validate_corpus(parts)


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
    feedback = TelemetryReader().load(feedback_jsonl_path(data_dir))
    report = evaluate(loaded, run_id=args.run_id, feedback=feedback)
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

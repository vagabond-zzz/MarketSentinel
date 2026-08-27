from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from market_sentinel.clock import Clock, SystemClock
from market_sentinel.domain.enums import FeedStatus
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.health.policy import HealthPolicy
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.session import is_same_session
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist
from tools.live_probe.common import MIN_INTERVAL_S, clamp_interval

PRIMARY_SYMBOLS = ("600519.SH", "000001.SZ")
TEN_SYMBOL_BATCH = (
    "600519.SH",
    "000001.SZ",
    "600036.SH",
    "601318.SH",
    "000858.SZ",
    "002415.SZ",
    "600276.SH",
    "000333.SZ",
    "601166.SH",
    "600900.SH",
)
DEFAULT_SAMPLES = 20
MAX_ALERT_TICKS = 8


@dataclass
class TickSample:
    symbol: str
    price: float
    volume: float
    high: float
    low: float
    turnover: float | None
    market_timestamp: float
    received_timestamp: float
    latency_s: float
    feed_status: str
    accepted_events: int
    alert_candidates: int
    context_create_count: int


@dataclass
class BatchSample:
    size: int
    symbols: tuple[str, ...]
    returned: tuple[str, ...]
    context_create_count: int
    turnover_all_none: bool


@dataclass
class SessionReport:
    passed: bool
    failures: list[str]
    notes: list[str]
    ticks: list[TickSample] = field(default_factory=list)
    batches: list[BatchSample] = field(default_factory=list)
    positive_volume_deltas: int = 0
    max_latency_s: float | None = None
    feed_statuses: list[str] = field(default_factory=list)
    context_create_count: int = 0
    out_of_order_count: int = 0
    alert_ticks: int = 0

    def to_record(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_volume_series(timestamps: Sequence[float], volumes: Sequence[float]) -> list[str]:
    failures: list[str] = []
    if len(volumes) < 2:
        return ["volume series too short"]
    positive = 0
    for index in range(1, len(volumes)):
        previous = volumes[index - 1]
        current = volumes[index]
        if current + 1e-9 < previous:
            if is_same_session(timestamps[index - 1], timestamps[index]):
                failures.append(
                    f"same-session volume decreased {previous} -> {current} at sample {index}"
                )
        elif current > previous + 1e-9:
            positive += 1
    if positive == 0:
        failures.append(
            "no positive same-session volume delta observed; "
            "all-zero deltas are not success (run during A-share hours or extend sampling)"
        )
    return failures


def evaluate_session(
    ticks: Sequence[TickSample],
    batches: Sequence[BatchSample],
    *,
    expected_primary: Sequence[str],
    policy: HealthPolicy | None = None,
    context_create_count: int,
    out_of_order_count: int,
) -> SessionReport:
    health = policy or HealthPolicy()
    failures: list[str] = []
    notes: list[str] = []
    if health.delayed_s != 3.0 or health.stale_s != 30.0:
        failures.append("HealthPolicy thresholds changed; v0.4 must not widen delayed_s")
    if context_create_count != 1:
        failures.append(f"expected one AsyncQuoteContext, created {context_create_count}")
    if out_of_order_count:
        failures.append(f"out-of-order quotes observed: {out_of_order_count}")

    by_symbol: dict[str, list[TickSample]] = {}
    alert_ticks = 0
    statuses: set[str] = set()
    latencies: list[float] = []
    for sample in ticks:
        by_symbol.setdefault(sample.symbol, []).append(sample)
        statuses.add(sample.feed_status)
        latencies.append(sample.latency_s)
        if sample.turnover is not None:
            failures.append(f"{sample.symbol} turnover was {sample.turnover}, expected None")
        if sample.high < sample.low or sample.high <= 0 or sample.low <= 0:
            failures.append(
                f"{sample.symbol} high/low not sane high={sample.high} low={sample.low}"
            )
        if sample.market_timestamp == sample.received_timestamp:
            failures.append(f"{sample.symbol} market_timestamp equals received_timestamp")
        if sample.feed_status not in {FeedStatus.LIVE.value, FeedStatus.DELAYED.value}:
            failures.append(
                f"{sample.symbol} feed_status={sample.feed_status} on a successful quote"
            )
        if sample.alert_candidates:
            alert_ticks += 1
        if (
            sample.latency_s + 1e-9 >= health.delayed_s
            and sample.feed_status == FeedStatus.LIVE.value
        ):
            failures.append(
                f"{sample.symbol} latency {sample.latency_s:.3f}s should be DELAYED "
                f"(delayed_s={health.delayed_s})"
            )
        if (
            sample.latency_s + 1e-9 < health.delayed_s
            and sample.feed_status == FeedStatus.DELAYED.value
        ):
            failures.append(
                f"{sample.symbol} marked DELAYED with latency {sample.latency_s:.3f}s "
                f"< delayed_s={health.delayed_s}"
            )

    missing_primary = [symbol for symbol in expected_primary if symbol not in by_symbol]
    if missing_primary:
        failures.append(f"missing primary symbols: {missing_primary}")

    positive_total = 0
    for symbol, series in by_symbol.items():
        series = sorted(series, key=lambda item: item.received_timestamp)
        volumes = [item.volume for item in series]
        stamps = [item.market_timestamp for item in series]
        volume_failures = evaluate_volume_series(stamps, volumes)
        for item in volume_failures:
            if item.startswith("no positive"):
                continue
            failures.append(f"{symbol}: {item}")
        if not any(item.startswith("no positive") for item in volume_failures):
            positive_total += 1
        latest = series[0].market_timestamp
        for item in series[1:]:
            if item.market_timestamp < latest:
                failures.append(f"{symbol} market_timestamp rewound")
            latest = max(latest, item.market_timestamp)

    if positive_total == 0 and by_symbol:
        failures.append("no primary symbol showed a positive same-session volume delta")

    if alert_ticks > MAX_ALERT_TICKS:
        failures.append(f"alert storm: {alert_ticks} ticks produced alert_candidates")

    seen_sizes: set[int] = set()
    for batch in batches:
        seen_sizes.add(batch.size)
        if batch.context_create_count != 1:
            failures.append(f"batch size {batch.size} created extra SDK context")
        if set(batch.returned) != set(batch.symbols):
            failures.append(
                f"batch size {batch.size} missing symbols "
                f"{sorted(set(batch.symbols) - set(batch.returned))}"
            )
        if not batch.turnover_all_none:
            failures.append(f"batch size {batch.size} had non-None turnover")
    for size in (1, 2, 10):
        if size not in seen_sizes:
            failures.append(f"missing {size}-symbol batch observation")

    if FeedStatus.LIVE.value in statuses:
        notes.append("feed observed LIVE")
    if FeedStatus.DELAYED.value in statuses:
        notes.append("feed observed DELAYED (truthful; delayed_s not widened)")

    return SessionReport(
        passed=not failures,
        failures=failures,
        notes=notes,
        ticks=list(ticks),
        batches=list(batches),
        positive_volume_deltas=positive_total,
        max_latency_s=max(latencies) if latencies else None,
        feed_statuses=sorted(statuses),
        context_create_count=context_create_count,
        out_of_order_count=out_of_order_count,
        alert_ticks=alert_ticks,
    )


async def run_session_smoke(
    *,
    clock: Clock | None = None,
    provider: LongbridgeQuoteProvider | None = None,
    primary: Sequence[str] = PRIMARY_SYMBOLS,
    ten: Sequence[str] = TEN_SYMBOL_BATCH,
    samples: int = DEFAULT_SAMPLES,
    interval_s: float = MIN_INTERVAL_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> SessionReport:
    interval = clamp_interval(interval_s)
    if samples < 2:
        raise ValueError("samples must be >= 2")
    clock = clock or SystemClock()
    provider = provider or LongbridgeQuoteProvider(clock)
    watchlist = Watchlist(persist=False)
    for symbol in primary:
        watchlist.add(symbol)
    scheduler = AdaptiveScheduler(
        clock,
        SchedulerPolicy(
            cold_interval_s=0.0,
            warm_interval_s=0.0,
            hot_interval_s=0.0,
            hot_downgrade_dwell_s=0.0,
            warm_downgrade_dwell_s=0.0,
        ),
    )
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=scheduler,
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    ticks: list[TickSample] = []
    for index in range(samples):
        result = await engine.tick()
        for symbol in primary:
            if symbol not in engine._fetched_symbols:
                raise RuntimeError(f"missing live snapshot for {symbol}")
            state = engine.states.get(symbol)
            snapshot = None if state is None else state.latest
            row = result.for_symbol(symbol)
            if snapshot is None:
                raise RuntimeError(f"missing live snapshot for {symbol}")
            latency = max(0.0, snapshot.received_timestamp - snapshot.market_timestamp)
            ticks.append(
                TickSample(
                    symbol=symbol,
                    price=snapshot.price,
                    volume=snapshot.volume,
                    high=snapshot.high,
                    low=snapshot.low,
                    turnover=snapshot.turnover,
                    market_timestamp=snapshot.market_timestamp,
                    received_timestamp=snapshot.received_timestamp,
                    latency_s=latency,
                    feed_status=(state.feed_status.value if state is not None else "UNKNOWN"),
                    accepted_events=0 if row is None else len(row.accepted_events),
                    alert_candidates=0 if row is None else len(row.alert_candidates),
                    context_create_count=provider.diagnostics.context_create_count,
                )
            )
        if index + 1 < samples:
            await sleep(interval)

    batches: list[BatchSample] = []
    for requested in (tuple(primary[:1]), tuple(primary[:2]), tuple(ten)):
        snapshots = await provider.fetch_quotes(list(requested))
        batches.append(
            BatchSample(
                size=len(requested),
                symbols=tuple(requested),
                returned=tuple(item.symbol for item in snapshots),
                context_create_count=provider.diagnostics.context_create_count,
                turnover_all_none=all(item.turnover is None for item in snapshots),
            )
        )
        await sleep(interval)

    return evaluate_session(
        ticks,
        batches,
        expected_primary=primary,
        context_create_count=provider.diagnostics.context_create_count,
        out_of_order_count=engine.diagnostics.out_of_order_count,
    )


def write_report(path: str, report: SessionReport) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    compact = {
        "passed": report.passed,
        "failures": report.failures,
        "notes": report.notes,
        "positive_volume_deltas": report.positive_volume_deltas,
        "max_latency_s": report.max_latency_s,
        "feed_statuses": report.feed_statuses,
        "context_create_count": report.context_create_count,
        "out_of_order_count": report.out_of_order_count,
        "alert_ticks": report.alert_ticks,
        "tick_count": len(report.ticks),
        "batches": [
            {
                "size": item.size,
                "returned": list(item.returned),
                "context_create_count": item.context_create_count,
            }
            for item in report.batches
        ],
    }
    target.write_text(json.dumps(compact, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="v0.4 Longbridge A-share live session smoke (not default CI)."
    )
    parser.add_argument("--symbols", default=",".join(PRIMARY_SYMBOLS))
    parser.add_argument("--ten", default=",".join(TEN_SYMBOL_BATCH))
    parser.add_argument("--interval", type=float, default=MIN_INTERVAL_S)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--out", default=".tmp/longbridge_session_smoke.json")
    args = parser.parse_args(argv)
    primary = tuple(item.strip() for item in args.symbols.split(",") if item.strip())
    ten = tuple(item.strip() for item in args.ten.split(",") if item.strip())
    try:
        report = asyncio.run(
            run_session_smoke(
                primary=primary,
                ten=ten,
                samples=args.samples,
                interval_s=args.interval,
            )
        )
    except Exception as exc:
        print(f"session smoke failed: {exc}", file=sys.stderr)
        return 2
    summary = dict(report.to_record())
    summary["ticks"] = f"{len(report.ticks)} samples omitted"
    print(json.dumps(summary, indent=2))
    if args.out:
        write_report(args.out, report)
    if not report.passed:
        print("FAILURES:", file=sys.stderr)
        for item in report.failures:
            print(f"- {item}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

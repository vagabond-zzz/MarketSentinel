"""Full-session benchmark: deterministic multi-symbol replay.

Generates a synthetic but realistic A-share trading day (10 symbols, both cash
sessions, 10s cadence) with injected surge/wobble windows, then runs the full
MarketEngine (features -> events -> signal pipeline -> warming/scheduler ->
MarketState) plus the IntelligenceCoordinator wired to a Fake provider, and
reports benchmark-grade metrics: quote/event/signal counts, LLM trigger share,
per-tick latency (avg/p50/p95/max), scheduler level distribution, and
surge-start -> first-alert detection latency in market seconds.

Run from repo root:  uv run python tools/resume_benchmark.py
Deterministic: seeded RNG; same output every run on the same machine class.
"""

from __future__ import annotations

import asyncio
import json
import random
import statistics
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_sentinel.clock import FakeClock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.orchestration.warming import WarmingPolicy
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.cooldown import CooldownGate
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.watchlist.watchlist import Watchlist

REPO = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO / ".tmp" / "bench_full_day.jsonl"
REPORT_PATH = REPO / ".tmp" / "resume_benchmark_report.json"
SEED = 20260830
STEP_S = 10.0
CST = timezone(timedelta(hours=8))

SYMBOLS: list[tuple[str, float]] = [
    ("600519.SH", 128.0),
    ("000001.SZ", 12.6),
    ("300750.SZ", 188.0),
    ("601318.SH", 56.0),
    ("000858.SZ", 148.0),
    ("600036.SH", 36.5),
    ("002415.SZ", 42.0),
    ("601899.SH", 15.8),
    ("000333.SZ", 74.0),
    ("600276.SH", 66.0),
]

# (name, start_epoch, per-symbol batch-index windows)
MORNING = (datetime(2024, 1, 15, 9, 30, tzinfo=CST), datetime(2024, 1, 15, 11, 30, tzinfo=CST))
AFTERNOON = (datetime(2024, 1, 15, 13, 0, tzinfo=CST), datetime(2024, 1, 15, 15, 0, tzinfo=CST))


def _session_batches(start: datetime, end: datetime) -> list[float]:
    ts = start.timestamp()
    stop = end.timestamp()
    out: list[float] = []
    while ts < stop:
        out.append(ts)
        ts += STEP_S
    return out


def _build_batches() -> tuple[list[list[dict]], dict[str, list[tuple[float, float]]]]:
    rng = random.Random(SEED)
    morning = _session_batches(*MORNING)
    afternoon = _session_batches(*AFTERNOON)
    timeline = morning + afternoon
    sessions = [(morning, 0), (afternoon, len(morning))]

    # per symbol: 3 surge windows (strong, alert-worthy) + 2 mild wobble windows.
    # surge windows avoid the lunch boundary (morning 0..719, afternoon 720..1439).
    surges: dict[str, list[tuple[int, int, int]]] = {}  # (start_idx, end_idx, dir)
    wobbles: dict[str, list[tuple[int, int, int]]] = {}
    for i, (symbol, _) in enumerate(SYMBOLS):
        starts = [252 + (i * 9) % 60, 842 + (i * 13) % 60, 1120 + (i * 7) % 80]
        dirs = [1, -1, 1 if i % 2 == 0 else -1]
        windows = []
        for s, d in zip(starts, dirs):
            length = rng.randint(20, 34)  # 200-340 seconds
            windows.append((s, s + length, d))
        surges[symbol] = windows
        wob_specs = [
            (430 + (i * 11) % 40, 1 if i % 3 else -1),
            (1000 + (i * 5) % 40, -1 if i % 3 else 1),
        ]
        wobbles[symbol] = [(s, s + rng.randint(14, 22), d) for s, d in wob_specs]

    # price multiplier plan per symbol per batch index
    plans: dict[str, dict[int, tuple[float, float]]] = {}  # idx -> (step_pct, vol_mult)
    for i, (symbol, base) in enumerate(SYMBOLS):
        plan: dict[int, tuple[float, float]] = {}
        for idx in range(len(timeline)):
            plan[idx] = (rng.gauss(0.0, 0.0008), 1.0)
        for w_idx, (s, e, d) in enumerate(surges[symbol]):
            move = rng.uniform(0.018, 0.042) * d  # 1.8%-4.2% total move
            vol_max = rng.uniform(5.0, 12.0)
            n = e - s
            for k in range(n):
                # front-loaded impulse: price and volume arrive at the head of
                # the window (real-world 放量 leads price), then decay.
                weight = 2.0 * (n - k) / (n * (n + 1))
                plan[s + k] = (
                    move * weight + rng.gauss(0.0, 0.0004),
                    1.0 + (vol_max - 1.0) * (1.0 - k / n),
                )
        for s, e, d in wobbles[symbol]:
            move = rng.uniform(0.010, 0.016) * d  # ~1.0-1.6% total -> sev2 1m moves
            n = e - s
            for k in range(n):
                plan[s + k] = (move / n + rng.gauss(0.0, 0.0003), rng.uniform(1.2, 1.7))
        plans[symbol] = plan

    batches: list[list[dict]] = [[] for _ in timeline]
    surge_spans: dict[str, list[tuple[float, float]]] = {}
    for i, (symbol, base) in enumerate(SYMBOLS):
        plan = plans[symbol]
        price = base * (1 + rng.uniform(-0.003, 0.003))
        for session_ts_list, offset in sessions:
            cum_volume = 0.0
            cum_turnover = 0.0
            v0 = 260.0 + i * 37.0
            for k, ts in enumerate(session_ts_list):
                idx = offset + k
                step_pct, vol_mult = plan[idx]
                price = price * (1 + step_pct)
                wig = rng.uniform(0.0002, 0.0009)
                high = price * (1 + wig)
                low = price * (1 - wig)
                step_volume = v0 * vol_mult * rng.uniform(0.85, 1.15)
                cum_volume += step_volume
                cum_turnover += step_volume * price
                row = {
                    "symbol": symbol,
                    "price": round(price, 3),
                    "open": round(base, 3),
                    "high": round(high, 3),
                    "low": round(low, 3),
                    "prev_close": round(base, 3),
                    "volume": round(cum_volume, 1),
                    "turnover": round(cum_turnover, 1),
                    "market_timestamp": ts,
                }
                batches[idx].append(row)
    surge_spans: dict[str, list[tuple[float, float]]] = {
        symbol: [
            (timeline[s], timeline[min(e, len(timeline) - 1)] + STEP_S)
            for (s, e, _d) in surges[symbol]
        ]
        for symbol in surges
    }
    return batches, surge_spans


def _pct(values: list[float], pct: float) -> float:
    """Nearest-rank percentile, matching evaluation/stats.py convention."""
    if not values:
        return 0.0
    import math

    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def _telemetry_name(event: object) -> str:
    name = getattr(event, "name", None)
    return getattr(name, "value", str(name))


async def _run() -> dict:
    batches, surge_spans = _build_batches()
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(
        "\n".join(json.dumps(batch, separators=(",", ":")) for batch in batches) + "\n",
        encoding="utf-8",
    )
    quotes = sum(len(batch) for batch in batches)
    market_first = float(batches[0][0]["market_timestamp"])
    market_last = float(batches[-1][0]["market_timestamp"])

    start = market_first
    clock = FakeClock(wall=start, monotonic=0.0)
    watchlist = Watchlist(persist=False)
    for symbol, _ in SYMBOLS:
        watchlist.add(symbol)
    collector = InMemoryTelemetryCollector()
    telemetry = TelemetryRuntime(clock, collector)
    provider = ReplayProvider(FIXTURE_PATH, clock)
    coordinator = IntelligenceCoordinator(
        FakeIntelligenceProvider(),
        clock,
        timeout_s=8.0,
        telemetry=telemetry,
    )
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock, SchedulerPolicy()),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        pipeline=SignalPipeline(
            clock,
            composer=SignalComposer(clock, lookback_s=90.0),
            cooldown=CooldownGate(clock),
            telemetry=telemetry,
        ),
        warming=WarmingPolicy(),
        intelligence=coordinator,
        telemetry=telemetry,
    )

    await coordinator.start()
    tick_ms: list[float] = []
    level_counter: dict[str, int] = {}
    detection_latencies: list[float] = []
    span_alerted: set[int] = set()
    prev_ts = start
    for batch in batches:
        ts = float(batch[0]["market_timestamp"])
        clock.set_wall(ts)
        clock.advance_monotonic(max(0.0, ts - prev_ts))
        prev_ts = ts
        t0 = time.perf_counter()
        result = await engine.tick()
        tick_ms.append((time.perf_counter() - t0) * 1000.0)
        # yield so the intelligence worker drains its queue between ticks
        # (in production real fetch/IO sleeps provide this yield naturally).
        await asyncio.sleep(0)
        for item in result.symbol_results:
            if item.level_after is not None:
                key = item.level_after.value
                level_counter[key] = level_counter.get(key, 0) + 1
            if not item.alert_candidates:
                continue
            for span_idx, (span_start, span_end) in enumerate(surge_spans.get(item.symbol, [])):
                span_key = id(item.symbol) * 100000 + span_idx
                if span_key in span_alerted:
                    continue
                if span_start <= ts <= span_end + 90.0:
                    span_alerted.add(span_key)
                    detection_latencies.append(ts - span_start)
                    break
    # drain the intelligence worker (fake provider completes instantly)
    for _ in range(500):
        depth = getattr(coordinator.diagnostics, "queue_depth", 0)
        if depth == 0:
            break
        await asyncio.sleep(0.01)
    await coordinator.shutdown()

    name_counts: dict[str, int] = {}
    for event in collector.events:
        key = _telemetry_name(event)
        name_counts[key] = name_counts.get(key, 0) + 1
    diag = coordinator.diagnostics
    llm_submitted = int(getattr(diag, "requests_submitted", 0))
    episodes = int(name_counts.get("signal_episode_created", 0))
    candidates = int(name_counts.get("alert_candidate", 0))
    generated = int(name_counts.get("event_generated", 0))
    deduped = int(name_counts.get("event_deduped", 0))

    def ratio(num: int, den: int) -> float:
        return round(num / den * 100.0, 1) if den else 0.0

    report = {
        "fixture": str(FIXTURE_PATH),
        "seed": SEED,
        "symbols": len(SYMBOLS),
        "ticks": len(batches),
        "quotes": quotes,
        "market_span_hours": round((market_last - market_first) / 3600.0, 2),
        "session_hours": 4.0,
        "events_generated": generated,
        "events_deduped": deduped,
        "events_accepted": generated - deduped,
        "signal_episodes_created": episodes,
        "signal_escalated": int(name_counts.get("signal_escalated", 0)),
        "alert_candidates": candidates,
        "alert_suppressed": int(name_counts.get("alert_suppressed", 0)),
        "llm_requests_submitted": llm_submitted,
        "llm_skipped": int(getattr(diag, "requests_suppressed", 0)),
        "llm_share_of_episodes_pct": ratio(llm_submitted, episodes),
        "llm_share_of_candidates_pct": ratio(llm_submitted, candidates),
        "candidates_share_of_events_pct": ratio(candidates, generated),
        "llm_share_of_events_pct": ratio(llm_submitted, generated),
        "tick_ms_avg": round(statistics.fmean(tick_ms), 2),
        "tick_ms_p50": round(_pct(tick_ms, 50), 2),
        "tick_ms_p95": round(_pct(tick_ms, 95), 2),
        "tick_ms_max": round(max(tick_ms), 2),
        "per_symbol_tick_ms_avg": round(statistics.fmean(tick_ms) / len(SYMBOLS), 3),
        "scheduler_level_ticks": level_counter,
        "detection_latency_market_s_median": round(statistics.median(detection_latencies), 1)
        if detection_latencies
        else None,
        "detection_latency_market_s_p95": round(_pct(detection_latencies, 95), 1)
        if detection_latencies
        else None,
        "detection_latency_samples": len(detection_latencies),
        "llm_fallback": int(getattr(diag, "fallback_count", 0)),
        "llm_dropped_backpressure": int(getattr(diag, "dropped_backpressure", 0)),
        "llm_stale_discard": int(getattr(diag, "stale_discard", 0)),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    report = asyncio.run(_run())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

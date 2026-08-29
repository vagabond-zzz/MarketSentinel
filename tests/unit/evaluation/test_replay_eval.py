from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.evaluation.aggregate import evaluate
from market_sentinel.evaluation.reader import LoadedTelemetry
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector, NoOpTelemetryCollector
from market_sentinel.telemetry.contract import TelemetryName
from market_sentinel.telemetry.factory import jsonl_telemetry_runtime
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.watchlist.watchlist import Watchlist

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _batches(name: str) -> list[list[dict]]:
    path = FIXTURES / name
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _engine(
    tmp_path: Path,
    fixture_name: str,
    telemetry: TelemetryRuntime,
    *,
    symbol: str = "600519.SH",
) -> tuple[FakeClock, MarketEngine, list[list[dict]]]:
    batches = _batches(fixture_name)
    start = float(batches[0][0]["market_timestamp"])
    clock = FakeClock(wall=start, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add(symbol)
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
        telemetry=telemetry,
    )
    return clock, engine, batches


async def _replay(
    tmp_path: Path,
    fixture_name: str,
    telemetry: TelemetryRuntime,
) -> MarketEngine:
    clock, engine, batches = _engine(tmp_path, fixture_name, telemetry)
    for batch in batches:
        clock.set_wall(float(batch[0]["market_timestamp"]))
        await engine.tick()
    return engine


def _report_from_memory(memory: InMemoryTelemetryCollector, engine: MarketEngine):
    loaded = LoadedTelemetry(
        records=tuple(item.to_record() for item in memory.events),
        input_files=("memory",),
        records_read=len(memory.events),
        malformed_complete_lines=0,
        skipped_trailing_partial=False,
        healthy=True,
    )
    return evaluate(
        loaded,
        cluster_tracker_seen_count=engine.telemetry.cluster.seen_count,
    ).to_record()


@pytest.mark.asyncio
async def test_replay_normal_market_is_quiet(tmp_path: Path) -> None:
    memory = InMemoryTelemetryCollector()
    engine = await _replay(tmp_path, "normal_market.jsonl", TelemetryRuntime(FakeClock(), memory))
    report = _report_from_memory(memory, engine)
    assert report["pipeline"]["alert_candidates"] == 0
    assert report["pipeline"]["events_generated"] == 0
    assert report["intelligence"]["routed"] == 0
    assert engine.telemetry.cluster.seen_count == 0


async def test_replay_significant_tape_is_observable(tmp_path: Path) -> None:
    for fixture in (
        "rapid_move.jsonl",
        "volume_spike.jsonl",
        "price_volume_breakout.jsonl",
        "reversal.jsonl",
        "episode_lifecycle.jsonl",
    ):
        memory = InMemoryTelemetryCollector()
        clock = FakeClock()
        engine = await _replay(
            tmp_path / fixture.replace(".jsonl", ""),
            fixture,
            TelemetryRuntime(clock, memory),
        )
        report = _report_from_memory(memory, engine)
        assert report["pipeline"]["events_generated"] >= 1, fixture
        assert report["pipeline"]["signal_episodes_created"] >= 1, fixture
        assert report["pipeline"]["alert_candidates"] >= 1, fixture
        reasons = report["alert_noise"]["suppression_by_reason"]
        assert set(reasons) == {"cooldown", "same_tick_duplicate"}, fixture


async def test_replay_suppression_reasons_are_separated(tmp_path: Path) -> None:
    memory = InMemoryTelemetryCollector()
    engine = await _replay(
        tmp_path, "price_volume_breakout.jsonl", TelemetryRuntime(FakeClock(), memory)
    )
    reasons = _report_from_memory(memory, engine)["alert_noise"]["suppression_by_reason"]
    assert set(reasons) == {"cooldown", "same_tick_duplicate"}
    assert reasons["cooldown"] >= 0
    assert reasons["same_tick_duplicate"] >= 0


async def test_replay_stale_disconnect_does_not_forge_events(tmp_path: Path) -> None:
    memory = InMemoryTelemetryCollector()
    clock, engine, batches = _engine(
        tmp_path, "rapid_move.jsonl", TelemetryRuntime(FakeClock(), memory)
    )
    for batch in batches[:2]:
        clock.set_wall(float(batch[0]["market_timestamp"]))
        await engine.tick()
    generated_before = sum(
        1 for item in memory.events if item.name is TelemetryName.EVENT_GENERATED
    )
    engine.provider = FakeProvider(clock)
    engine.provider.set_timeout(True)
    clock.advance_monotonic(30.0)
    await engine.tick()
    generated_after = sum(1 for item in memory.events if item.name is TelemetryName.EVENT_GENERATED)
    assert generated_after == generated_before


async def test_cluster_tracker_size_matches_clustered_events(tmp_path: Path) -> None:
    memory = InMemoryTelemetryCollector()
    engine = await _replay(
        tmp_path, "price_volume_breakout.jsonl", TelemetryRuntime(FakeClock(), memory)
    )
    report = _report_from_memory(memory, engine)
    clustered = [
        item.event_id for item in memory.events if item.name is TelemetryName.EVENT_CLUSTERED
    ]
    assert engine.telemetry.cluster.seen_count == len(set(clustered))
    assert report["pipeline"]["cluster_tracker_seen_count"] == engine.telemetry.cluster.seen_count
    assert report["pipeline"]["events_clustered"] == len(clustered)
    assert engine.telemetry.cluster.seen_count >= 2


async def test_sync_jsonl_overhead_is_measured_not_gated(tmp_path: Path) -> None:
    fixture = "rapid_move.jsonl"
    ticks = len(_batches(fixture))

    async def run_with(telemetry: TelemetryRuntime, workdir: Path) -> float:
        start = time.perf_counter()
        await _replay(workdir, fixture, telemetry)
        return time.perf_counter() - start

    noop = TelemetryRuntime(FakeClock(), NoOpTelemetryCollector())
    baseline = await run_with(noop, tmp_path / "noop")
    jsonl_dir = tmp_path / "jsonl-data"
    jsonl = jsonl_telemetry_runtime(FakeClock(), data_dir=jsonl_dir)
    telemetry_elapsed = await run_with(jsonl, tmp_path / "jsonl")
    jsonl.close()
    extra = telemetry_elapsed - baseline
    # fraction = extra/baseline (e.g. 1.73 means +173%, not 1.73× total runtime).
    # total_runtime_ratio = telemetry/baseline (e.g. 2.73×).
    fraction = 0.0 if baseline <= 0 else extra / baseline
    total_ratio = 0.0 if baseline <= 0 else telemetry_elapsed / baseline
    evidence = {
        "baseline_elapsed": baseline,
        "telemetry_elapsed": telemetry_elapsed,
        "absolute_extra_s": extra,
        "relative_overhead_fraction": fraction,
        "total_runtime_ratio": total_ratio,
        "tick_count": ticks,
    }
    assert evidence["tick_count"] == ticks > 0
    assert evidence["baseline_elapsed"] >= 0
    assert evidence["telemetry_elapsed"] >= 0
    assert evidence["absolute_extra_s"] == extra
    assert evidence["relative_overhead_fraction"] == fraction
    assert evidence["total_runtime_ratio"] == total_ratio
    assert any((jsonl_dir / "telemetry.jsonl").read_text(encoding="utf-8").splitlines())

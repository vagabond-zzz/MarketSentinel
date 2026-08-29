from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.errors import TuningConfigError
from market_sentinel.evaluation.aggregate import evaluate
from market_sentinel.evaluation.reader import TelemetryReader
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.orchestration.warming import WarmingConfig
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.signals.cluster import CLUSTER_LOOKBACK_S
from market_sentinel.telemetry.contract import (
    FEEDBACK_ALLOWLIST,
    TELEMETRY_DENYLIST,
    FeedbackLabel,
    TuningSource,
)
from market_sentinel.telemetry.factory import jsonl_telemetry_runtime
from market_sentinel.telemetry.paths import feedback_jsonl_path, telemetry_jsonl_path
from market_sentinel.telemetry.user_feedback import parse_user_feedback
from market_sentinel.tuning.compare import compare_artifacts
from market_sentinel.tuning.config import (
    DEFERRED_TUNING_PARAMETER_NAMES,
    OFFLINE_TUNING_CONFIG_ALLOWLIST,
    OfflineTuningConfig,
    capture_baseline_config,
)
from market_sentinel.tuning.feedback import build_tuning_feedback_dataset
from market_sentinel.tuning.replay import default_fixture_dir
from market_sentinel.tuning.report import (
    RECOMMENDATION_DENIED_KEYS,
    TUNING_COMPARISON_SCHEMA_VERSION,
)
from market_sentinel.tuning.store import (
    TUNING_ARTIFACT_SCHEMA_VERSION,
    make_artifact,
    write_snapshot,
)
from market_sentinel.watchlist.watchlist import Watchlist

FIXTURES = default_fixture_dir()
_SYMBOL = "00700.HK"


def _batches(path: Path) -> list[list[dict]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@pytest.mark.integration
async def test_v06_release_smoke_telemetry_jsonl_and_report(tmp_path: Path) -> None:
    data_dir = tmp_path / "ms-data"
    fixture = FIXTURES / "rapid_move.jsonl"
    batches = _batches(fixture)
    start = float(batches[0][0]["market_timestamp"])
    clock = FakeClock(wall=start, monotonic=0.0)
    telemetry = jsonl_telemetry_runtime(clock, data_dir=data_dir)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add(_SYMBOL)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=ReplayProvider(fixture, clock),
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(cold_interval_s=0.0, warm_interval_s=0.0, hot_interval_s=0.0),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        telemetry=telemetry,
    )
    try:
        for batch in batches:
            clock.set_wall(float(batch[0]["market_timestamp"]))
            await engine.tick()
    finally:
        engine.telemetry.close()

    path = telemetry_jsonl_path(data_dir)
    assert path.is_file()
    loaded = TelemetryReader().load(path)
    assert loaded.healthy is True
    assert loaded.records_read >= 1
    run_ids = {row["run_id"] for row in loaded.records}
    assert run_ids == {engine.telemetry.run_id}
    assert any(isinstance(row.get("market_timestamp"), int | float) for row in loaded.records)
    report = evaluate(loaded).to_record()
    assert report["pipeline"]["events_generated"] >= 1
    for row in loaded.records:
        assert TELEMETRY_DENYLIST.isdisjoint(row)


@pytest.mark.integration
async def test_v06_release_smoke_explicit_feedback(tmp_path: Path) -> None:
    data_dir = tmp_path / "ms-data"
    fixture = FIXTURES / "rapid_move.jsonl"
    batches = _batches(fixture)
    start = float(batches[0][0]["market_timestamp"])
    clock = FakeClock(wall=start, monotonic=0.0)
    telemetry = jsonl_telemetry_runtime(clock, data_dir=data_dir)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add(_SYMBOL)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=ReplayProvider(fixture, clock),
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(cold_interval_s=0.0, warm_interval_s=0.0, hot_interval_s=0.0),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
        telemetry=telemetry,
    )
    try:
        for batch in batches:
            clock.set_wall(float(batch[0]["market_timestamp"]))
            await engine.tick()
        tel_loaded = TelemetryReader().load(telemetry_jsonl_path(data_dir))
        empty = evaluate(tel_loaded).to_record()
        assert empty["explicit_feedback"]["useful_rate"]["available"] is False
        signal_id = next(
            row["signal_id"]
            for row in tel_loaded.records
            if row.get("name") == "alert_candidate" and isinstance(row.get("signal_id"), str)
        )
        engine.telemetry.record_feedback(
            signal_id=signal_id,
            label=FeedbackLabel.USEFUL,
            created_timestamp=clock.wall_time(),
        )
        rejected = parse_user_feedback(
            {
                "protocol_version": 1,
                "type": "user_feedback",
                "request_id": "fb1",
                "signal_id": signal_id,
                "feedback_type": "useful",
                "created_timestamp": 1.0,
                "notes": "free text",
            }
        )
        assert isinstance(rejected, str)
    finally:
        engine.telemetry.close()

    fb_path = feedback_jsonl_path(data_dir)
    assert fb_path.is_file()
    tel = TelemetryReader().load(telemetry_jsonl_path(data_dir))
    fb = TelemetryReader().load(fb_path)
    report = evaluate(tel, feedback=fb).to_record()
    assert report["explicit_feedback"]["feedback_count"] == 1
    assert report["explicit_feedback"]["useful_count"] == 1
    dataset = build_tuning_feedback_dataset(fb.records, tel.records)
    assert dataset.eligible_target_count == 1
    assert dataset.orphan_feedback_count == 0
    for row in fb.records:
        assert TELEMETRY_DENYLIST.isdisjoint(row)
        assert "notes" not in row
    assert FEEDBACK_ALLOWLIST.isdisjoint({"notes", "title", "summary", "prompt"})


@pytest.mark.integration
async def test_v06_release_smoke_offline_tuning(tmp_path: Path) -> None:
    data_dir = tmp_path / "ms-data"
    baseline_cfg = capture_baseline_config()
    assert set(baseline_cfg.to_record()) == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)
    baseline = make_artifact(
        baseline_cfg,
        config_version="baseline-release-smoke",
        source=TuningSource.OFFLINE_EVAL,
    )
    candidate_cfg = replace(baseline_cfg, warm_change_1m=0.99)
    candidate = make_artifact(
        candidate_cfg,
        config_version="candidate-warm-1m",
        source=TuningSource.MANUAL,
    )
    write_snapshot(data_dir, baseline)
    write_snapshot(data_dir, candidate)
    disk = json.loads(
        (data_dir / "tuning" / f"{baseline.snapshot.snapshot_id}.json").read_text(encoding="utf-8")
    )
    assert disk["schema_version"] == TUNING_ARTIFACT_SCHEMA_VERSION == 2
    report = await compare_artifacts(
        baseline,
        candidate,
        corpus=("pre_signal_warm",),
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "work",
    )
    record = report.to_record()
    assert record["schema_version"] == TUNING_COMPARISON_SCHEMA_VERSION == 2
    assert record["delta"]["scheduler"]["warm_tick_count"]["delta"] != 0
    assert record["data_quality"]["wrote_telemetry_jsonl"] is False
    assert record["data_quality"]["wrote_feedback_jsonl"] is False
    assert not telemetry_jsonl_path(data_dir).exists()
    assert not feedback_jsonl_path(data_dir).exists()
    assert capture_baseline_config().warm_change_1m == WarmingConfig().warm_change_1m
    assert CLUSTER_LOOKBACK_S == 90.0
    payload = capture_baseline_config().to_record()
    payload["cooldown_s"] = 1.0
    with pytest.raises(TuningConfigError, match="deferred"):
        OfflineTuningConfig.from_record(payload)
    assert "cooldown_s" in DEFERRED_TUNING_PARAMETER_NAMES
    keys = _all_keys(record)
    assert keys.isdisjoint(RECOMMENDATION_DENIED_KEYS)
    assert TELEMETRY_DENYLIST.isdisjoint(keys)


def _all_keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        found.update(payload)
        for value in payload.values():
            found.update(_all_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_all_keys(item))
    return found

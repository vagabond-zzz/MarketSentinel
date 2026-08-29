from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.signals.cluster import CLUSTER_LOOKBACK_S
from market_sentinel.telemetry.contract import TuningSource
from market_sentinel.tuning.compare import compare_artifacts, metrics_from_records
from market_sentinel.tuning.config import capture_baseline_config
from market_sentinel.tuning.replay import (
    DEFAULT_CORPUS,
    default_fixture_dir,
    run_tuned_replay,
    tick_facts,
)
from market_sentinel.tuning.report import (
    RECOMMENDATION_DENIED_KEYS,
    UNAVAILABLE_HOST_OFFLINE,
    UNAVAILABLE_INTEL_OFFLINE,
)
from market_sentinel.tuning.store import make_artifact

FIXTURES = default_fixture_dir()


def _artifact(config=None, *, version: str = "baseline-0.5.0"):
    return make_artifact(
        config if config is not None else capture_baseline_config(),
        config_version=version,
        source=TuningSource.OFFLINE_EVAL,
    )


async def test_baseline_replay_parity_with_normal_replay(tmp_path: Path) -> None:
    from tests.integration.test_replay_scenarios import _run

    engine, results = await _run(tmp_path, "rapid_move.jsonl")
    tuned = await run_tuned_replay(
        capture_baseline_config(),
        "rapid_move",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "tuned",
    )
    assert tuned.facts == tick_facts(results, "00700.HK")
    assert engine.states.get("00700.HK") is not None


async def test_baseline_equals_candidate_zero_behavioral_delta(tmp_path: Path) -> None:
    baseline = _artifact()
    candidate = _artifact(version="candidate-same")
    report = await compare_artifacts(
        baseline,
        candidate,
        corpus=("normal_market", "rapid_move"),
        fixture_dir=FIXTURES,
        work_dir=tmp_path,
    )
    record = report.to_record()
    delta = record["delta"]["pipeline"]
    for key in (
        "events_generated",
        "events_deduped",
        "events_clustered",
        "signal_episodes_created",
        "signal_escalations",
        "alert_candidates",
        "alert_suppressed",
    ):
        assert delta[key]["delta"] == 0
    noise = record["delta"]["noise"]
    for key in (
        "info_count",
        "notice_count",
        "important_count",
        "critical_count",
        "repeated_episode_signal_count",
        "repeated_episode_extra_alert_count",
    ):
        assert noise[key]["delta"] == 0
    assert noise["suppression_by_reason"]["cooldown"]["delta"] == 0
    assert noise["suppression_by_reason"]["same_tick_duplicate"]["delta"] == 0


async def test_candidate_run_does_not_pollute_subsequent_baseline(tmp_path: Path) -> None:
    first = await run_tuned_replay(
        capture_baseline_config(),
        "rapid_move",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "a",
    )
    await run_tuned_replay(
        replace(capture_baseline_config(), cluster_lookback_s=1.0),
        "rapid_move",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "cand",
    )
    second = await run_tuned_replay(
        capture_baseline_config(),
        "rapid_move",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "b",
    )
    assert first.facts == second.facts
    assert CLUSTER_LOOKBACK_S == 90.0
    assert SchedulerPolicy().cold_interval_s == 10.0
    assert capture_baseline_config().cluster_lookback_s == CLUSTER_LOOKBACK_S


async def test_fixed_corpus_and_fixture_before_after(tmp_path: Path) -> None:
    baseline = _artifact()
    candidate = _artifact(
        replace(capture_baseline_config(), cluster_lookback_s=1.0),
        version="candidate-lookback-001",
    )
    report = await compare_artifacts(
        baseline,
        candidate,
        corpus=DEFAULT_CORPUS,
        fixture_dir=FIXTURES,
        work_dir=tmp_path,
    )
    record = report.to_record()
    assert record["corpus"] == list(DEFAULT_CORPUS)
    ids = [row["corpus_id"] for row in record["per_fixture"]]
    assert ids == list(DEFAULT_CORPUS)
    dumped = json.dumps(record)
    assert "recommended" not in dumped
    assert "optimal" not in dumped
    assert "D:/" not in dumped and "C:\\" not in dumped
    assert record["baseline_metrics"]["pipeline"]["alerts_presented"]["unavailable_reason"] == (
        UNAVAILABLE_HOST_OFFLINE
    )
    assert record["candidate_metrics"]["intelligence"]["unavailable_reason"] == (
        UNAVAILABLE_INTEL_OFFLINE
    )
    assert record["data_quality"]["wrote_telemetry_jsonl"] is False
    assert record["data_quality"]["wrote_feedback_jsonl"] is False
    assert record["feedback_evidence"]["not_useful"] == 0
    assert record["data_quality"]["orphan_feedback_count"] == 0
    keys = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            keys.update(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(record)
    assert keys.isdisjoint(RECOMMENDATION_DENIED_KEYS)
    assert "workspace" not in keys
    assert "prompt" not in keys
    assert "title" not in keys


async def test_compare_does_not_write_telemetry_or_feedback_jsonl(
    tmp_path: Path, telemetry_data_dir: Path
) -> None:
    baseline = _artifact()
    candidate = _artifact(version="candidate-b")
    await compare_artifacts(
        baseline,
        candidate,
        corpus=("normal_market",),
        fixture_dir=FIXTURES,
        work_dir=tmp_path,
    )
    assert not (telemetry_data_dir / "telemetry.jsonl").exists()
    assert not (telemetry_data_dir / "feedback.jsonl").exists()


async def test_warming_candidate_changes_scheduler_level(tmp_path: Path) -> None:
    baseline = await run_tuned_replay(
        capture_baseline_config(),
        "pre_signal_warm",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "base",
    )
    candidate = await run_tuned_replay(
        replace(
            capture_baseline_config(),
            warm_change_1m=0.99,
            warm_change_5m=0.99,
            warm_volume_ratio=99.0,
        ),
        "pre_signal_warm",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "cand",
    )
    assert baseline.facts[-1]["level"] == "WARM"
    assert candidate.facts[-1]["level"] == "COLD"
    assert baseline.facts != candidate.facts


def test_metrics_keep_unavailable_without_host_or_intelligence() -> None:
    metrics = metrics_from_records(())
    assert metrics["pipeline"]["alerts_presented"]["available"] is False
    assert metrics["intelligence"]["available"] is False

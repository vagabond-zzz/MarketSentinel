from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from market_sentinel.errors import TuningConfigError, TuningSnapshotError
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
    validate_corpus,
)
from market_sentinel.tuning.report import (
    RECOMMENDATION_DENIED_KEYS,
    TUNING_COMPARISON_SCHEMA_VERSION,
    UNAVAILABLE_HOST_OFFLINE,
    UNAVAILABLE_INTEL_OFFLINE,
    TuningComparisonReport,
)
from market_sentinel.tuning.store import make_artifact

FIXTURES = default_fixture_dir()
_SCHEDULER_KEYS = (
    "cold_tick_count",
    "warm_tick_count",
    "hot_tick_count",
    "level_transition_count",
    "processed_tick_count",
)


def _artifact(config=None, *, version: str = "baseline-0.5.0"):
    return make_artifact(
        config if config is not None else capture_baseline_config(),
        config_version=version,
        source=TuningSource.OFFLINE_EVAL,
    )


def _assert_zero_delta(record: dict) -> None:
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
    scheduler = record["delta"]["scheduler"]
    for key in _SCHEDULER_KEYS:
        assert scheduler[key]["delta"] == 0


async def test_baseline_replay_parity_with_normal_replay(tmp_path: Path) -> None:
    from tests.integration.test_replay_scenarios import _run

    engine, results = await _run(tmp_path, "rapid_move.jsonl")
    tuned = await run_tuned_replay(
        capture_baseline_config(),
        "rapid_move",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "tuned",
    )
    assert tuned.facts == tick_facts(results, "600519.SH")
    assert engine.states.get("600519.SH") is not None


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
    assert record["schema_version"] == TUNING_COMPARISON_SCHEMA_VERSION == 2
    _assert_zero_delta(record)
    for row in record["per_fixture"]:
        assert set(row["baseline_metrics"]["scheduler"]) == set(_SCHEDULER_KEYS)
        assert set(row["candidate_metrics"]["scheduler"]) == set(_SCHEDULER_KEYS)
        for key in _SCHEDULER_KEYS:
            assert row["delta"]["scheduler"][key]["delta"] == 0


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
    assert record["schema_version"] == 2
    assert record["corpus"] == list(DEFAULT_CORPUS)
    ids = [row["corpus_id"] for row in record["per_fixture"]]
    assert ids == list(DEFAULT_CORPUS)
    dumped = json.dumps(record)
    assert "recommended" not in dumped
    assert "optimal" not in dumped
    assert "winner" not in dumped
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
    keys: set[str] = set()

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
    assert "scheduler" in keys
    assert "cold_tick_count" in keys


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


async def test_pre_signal_warm_warming_is_visible_in_comparison_report(tmp_path: Path) -> None:
    report = await compare_artifacts(
        _artifact(),
        _artifact(
            replace(capture_baseline_config(), warm_change_1m=0.99),
            version="candidate-warm-1m",
        ),
        corpus=("pre_signal_warm",),
        fixture_dir=FIXTURES,
        work_dir=tmp_path,
    )
    record = report.to_record()
    fixture = record["per_fixture"][0]
    assert fixture["baseline_metrics"]["scheduler"]["warm_tick_count"] == 1
    assert fixture["candidate_metrics"]["scheduler"]["warm_tick_count"] == 0
    assert fixture["delta"]["scheduler"]["warm_tick_count"]["delta"] != 0
    assert record["delta"]["scheduler"]["warm_tick_count"]["delta"] != 0


async def test_warming_candidate_changes_scheduler_level(tmp_path: Path) -> None:
    baseline = await run_tuned_replay(
        capture_baseline_config(),
        "pre_signal_warm",
        fixture_dir=FIXTURES,
        work_dir=tmp_path / "base",
    )
    candidate = await run_tuned_replay(
        replace(capture_baseline_config(), warm_change_1m=0.99),
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
    assert metrics["scheduler"] == {
        "cold_tick_count": 0,
        "warm_tick_count": 0,
        "hot_tick_count": 0,
        "level_transition_count": 0,
        "processed_tick_count": 0,
    }


def test_empty_and_duplicate_corpus_fail_closed() -> None:
    with pytest.raises(TuningConfigError, match="at least one corpus_id"):
        validate_corpus(())
    with pytest.raises(TuningConfigError, match="duplicate corpus_id"):
        validate_corpus(("rapid_move", "rapid_move"))


async def test_compare_empty_corpus_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(TuningConfigError, match="at least one corpus_id"):
        await compare_artifacts(
            _artifact(),
            _artifact(version="candidate-empty"),
            corpus=(),
            fixture_dir=FIXTURES,
            work_dir=tmp_path,
        )


async def test_compare_rejects_baseline_artifact_schema_v1(tmp_path: Path) -> None:
    with pytest.raises(TuningSnapshotError, match="unsupported tuning artifact schema_version"):
        await compare_artifacts(
            replace(_artifact(), schema_version=1),
            _artifact(version="candidate-v2"),
            corpus=("normal_market",),
            fixture_dir=FIXTURES,
            work_dir=tmp_path,
        )


async def test_compare_rejects_candidate_artifact_schema_v1(tmp_path: Path) -> None:
    with pytest.raises(TuningSnapshotError, match="unsupported tuning artifact schema_version"):
        await compare_artifacts(
            _artifact(),
            replace(_artifact(version="candidate-v1"), schema_version=1),
            corpus=("normal_market",),
            fixture_dir=FIXTURES,
            work_dir=tmp_path,
        )


async def test_invalid_artifact_schema_does_not_start_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def _forbidden(*_args: object, **_kwargs: object) -> object:
        calls.append("replay")
        raise AssertionError("run_tuned_replay must not run")

    monkeypatch.setattr("market_sentinel.tuning.compare.run_tuned_replay", _forbidden)
    with pytest.raises(TuningSnapshotError, match="unsupported tuning artifact schema_version"):
        await compare_artifacts(
            replace(_artifact(), schema_version=1),
            _artifact(version="candidate-v2"),
            corpus=("normal_market",),
            fixture_dir=FIXTURES,
            work_dir=tmp_path,
        )
    assert calls == []


def test_comparison_report_schema_v1_fail_closed() -> None:
    report = TuningComparisonReport(
        schema_version=1,
        baseline_snapshot={},
        candidate_snapshot={},
        baseline_config={},
        candidate_config={},
        corpus=["normal_market"],
        baseline_metrics={},
        candidate_metrics={},
        delta={},
        feedback_evidence={},
        data_quality={},
        per_fixture=[],
    )
    with pytest.raises(ValueError, match="unsupported tuning comparison schema_version"):
        report.to_record()

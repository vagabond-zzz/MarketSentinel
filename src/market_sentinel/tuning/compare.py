from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from market_sentinel.evaluation.aggregate import evaluate
from market_sentinel.evaluation.reader import LoadedTelemetry
from market_sentinel.telemetry.contract import SuppressionReason, TelemetryName
from market_sentinel.tuning.feedback import TuningFeedbackDataset
from market_sentinel.tuning.replay import DEFAULT_CORPUS, run_tuned_replay
from market_sentinel.tuning.report import (
    TUNING_COMPARISON_SCHEMA_VERSION,
    UNAVAILABLE_HOST_OFFLINE,
    UNAVAILABLE_INTEL_OFFLINE,
    TuningComparisonReport,
    unavailable_metric,
)
from market_sentinel.tuning.store import TuningArtifact

_CANDIDATE = TelemetryName.ALERT_CANDIDATE.value
_SUPPRESSED = TelemetryName.ALERT_SUPPRESSED.value
_PRIORITIES = {
    "INFO": "info_count",
    "NOTICE": "notice_count",
    "IMPORTANT": "important_count",
    "CRITICAL": "critical_count",
}
_PIPELINE_COUNTS = (
    "events_generated",
    "events_deduped",
    "events_clustered",
    "signal_episodes_created",
    "signal_escalations",
    "alert_candidates",
    "alert_suppressed",
)
_NOISE_COUNTS = (
    "info_count",
    "notice_count",
    "important_count",
    "critical_count",
    "repeated_episode_signal_count",
    "repeated_episode_extra_alert_count",
)


def _count(records: Sequence[dict[str, object]], name: str) -> int:
    return sum(1 for row in records if row.get("name") == name)


def _priority_counts(records: Sequence[dict[str, object]]) -> dict[str, int]:
    counts = {key: 0 for key in _PRIORITIES.values()}
    for row in records:
        if row.get("name") != _CANDIDATE:
            continue
        priority = row.get("priority")
        if not isinstance(priority, str):
            continue
        mapped = _PRIORITIES.get(priority.upper())
        if mapped is not None:
            counts[mapped] += 1
    return counts


def _repeated(records: Sequence[dict[str, object]]) -> tuple[int, int]:
    grouped: dict[tuple[str, str], int] = {}
    for row in records:
        if row.get("name") != _CANDIDATE:
            continue
        run_id = row.get("run_id")
        signal_id = row.get("signal_id")
        if not isinstance(run_id, str) or not isinstance(signal_id, str):
            continue
        grouped[(run_id, signal_id)] = grouped.get((run_id, signal_id), 0) + 1
    repeated = 0
    extra = 0
    for count in grouped.values():
        if count > 1:
            repeated += 1
            extra += count - 1
    return repeated, extra


def _suppression(records: Sequence[dict[str, object]]) -> dict[str, int]:
    counts = {item.value: 0 for item in SuppressionReason}
    for row in records:
        if row.get("name") != _SUPPRESSED:
            continue
        reason = row.get("suppression_reason")
        if isinstance(reason, str) and reason in counts:
            counts[reason] += 1
    return counts


def metrics_from_records(records: Sequence[dict[str, object]]) -> dict[str, object]:
    loaded = LoadedTelemetry(tuple(records), ("memory",), len(records), 0, False, True)
    evaluation = evaluate(loaded).to_record()
    repeated_signals, extra_alerts = _repeated(records)
    pipeline = {
        "events_generated": _count(records, TelemetryName.EVENT_GENERATED.value),
        "events_deduped": _count(records, TelemetryName.EVENT_DEDUPED.value),
        "events_clustered": _count(records, TelemetryName.EVENT_CLUSTERED.value),
        "signal_episodes_created": _count(records, TelemetryName.SIGNAL_EPISODE_CREATED.value),
        "signal_escalations": _count(records, TelemetryName.SIGNAL_ESCALATED.value),
        "alert_candidates": _count(records, _CANDIDATE),
        "alert_suppressed": _count(records, _SUPPRESSED),
        "alerts_presented": unavailable_metric(UNAVAILABLE_HOST_OFFLINE),
    }
    noise = {
        **_priority_counts(records),
        "suppression_by_reason": _suppression(records),
        "repeated_episode_signal_count": repeated_signals,
        "repeated_episode_extra_alert_count": extra_alerts,
        "alerts_per_market_hour": evaluation["alert_noise"]["alerts_per_market_hour"],
    }
    return {
        "pipeline": pipeline,
        "noise": noise,
        "intelligence": unavailable_metric(UNAVAILABLE_INTEL_OFFLINE),
    }


def _add_metrics(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    pipeline = {
        key: int(left["pipeline"][key]) + int(right["pipeline"][key])  # type: ignore[index]
        for key in _PIPELINE_COUNTS
    }
    pipeline["alerts_presented"] = unavailable_metric(UNAVAILABLE_HOST_OFFLINE)
    left_noise: dict[str, object] = left["noise"]  # type: ignore[assignment]
    right_noise: dict[str, object] = right["noise"]  # type: ignore[assignment]
    noise_counts = {key: int(left_noise[key]) + int(right_noise[key]) for key in _NOISE_COUNTS}
    left_sup = left_noise["suppression_by_reason"]
    right_sup = right_noise["suppression_by_reason"]
    suppression = {
        key: int(left_sup[key]) + int(right_sup[key])  # type: ignore[index]
        for key in ("cooldown", "same_tick_duplicate")
    }
    left_hour = left_noise["alerts_per_market_hour"]
    right_hour = right_noise["alerts_per_market_hour"]
    if (
        isinstance(left_hour, dict)
        and isinstance(right_hour, dict)
        and left_hour.get("available") is False
        and right_hour.get("available") is False
    ):
        hour = unavailable_metric(
            str(left_hour.get("unavailable_reason") or "unsupported_market_scope")
        )
    else:
        hour = unavailable_metric("incomparable_market_hour")
    return {
        "pipeline": pipeline,
        "noise": {
            **noise_counts,
            "suppression_by_reason": suppression,
            "alerts_per_market_hour": hour,
        },
        "intelligence": unavailable_metric(UNAVAILABLE_INTEL_OFFLINE),
    }


def _count_delta(baseline: int, candidate: int) -> dict[str, int]:
    return {"baseline": baseline, "candidate": candidate, "delta": candidate - baseline}


def _metric_delta(baseline: dict[str, object], candidate: dict[str, object]) -> dict[str, object]:
    pipeline: dict[str, object] = {
        key: _count_delta(
            int(baseline["pipeline"][key]),  # type: ignore[index]
            int(candidate["pipeline"][key]),  # type: ignore[index]
        )
        for key in _PIPELINE_COUNTS
    }
    pipeline["alerts_presented"] = unavailable_metric(UNAVAILABLE_HOST_OFFLINE)
    b_noise: dict[str, object] = baseline["noise"]  # type: ignore[assignment]
    c_noise: dict[str, object] = candidate["noise"]  # type: ignore[assignment]
    noise: dict[str, object] = {
        key: _count_delta(int(b_noise[key]), int(c_noise[key])) for key in _NOISE_COUNTS
    }
    b_sup: dict[str, int] = b_noise["suppression_by_reason"]  # type: ignore[assignment]
    c_sup: dict[str, int] = c_noise["suppression_by_reason"]  # type: ignore[assignment]
    noise["suppression_by_reason"] = {
        key: _count_delta(int(b_sup[key]), int(c_sup[key]))
        for key in ("cooldown", "same_tick_duplicate")
    }
    b_hour = b_noise["alerts_per_market_hour"]
    c_hour = c_noise["alerts_per_market_hour"]
    if (
        isinstance(b_hour, dict)
        and isinstance(c_hour, dict)
        and b_hour.get("available") is False
        and c_hour.get("available") is False
    ):
        noise["alerts_per_market_hour"] = unavailable_metric(
            str(b_hour.get("unavailable_reason") or "unsupported_market_scope")
        )
    else:
        noise["alerts_per_market_hour"] = unavailable_metric("incomparable_market_hour")
    return {
        "pipeline": pipeline,
        "noise": noise,
        "intelligence": unavailable_metric(UNAVAILABLE_INTEL_OFFLINE),
    }


def empty_feedback_dataset() -> TuningFeedbackDataset:
    return TuningFeedbackDataset(
        raw_feedback_count=0,
        semantic_valid_feedback_count=0,
        eligible_target_count=0,
        orphan_feedback_count=0,
        superseded_feedback_count=0,
        useful=0,
        not_useful=0,
        too_noisy=0,
        too_late=0,
    )


async def compare_artifacts(
    baseline: TuningArtifact,
    candidate: TuningArtifact,
    *,
    corpus: tuple[str, ...] = DEFAULT_CORPUS,
    fixture_dir: Path,
    work_dir: Path,
    feedback: TuningFeedbackDataset | None = None,
) -> TuningComparisonReport:
    evidence = feedback if feedback is not None else empty_feedback_dataset()
    per_fixture: list[dict[str, object]] = []
    totals_b: dict[str, object] | None = None
    totals_c: dict[str, object] | None = None
    for corpus_id in corpus:
        left = await run_tuned_replay(
            baseline.config, corpus_id, fixture_dir=fixture_dir, work_dir=work_dir
        )
        right = await run_tuned_replay(
            candidate.config, corpus_id, fixture_dir=fixture_dir, work_dir=work_dir
        )
        left_metrics = metrics_from_records(left.records)
        right_metrics = metrics_from_records(right.records)
        per_fixture.append(
            {
                "corpus_id": corpus_id,
                "baseline_metrics": left_metrics,
                "candidate_metrics": right_metrics,
                "delta": _metric_delta(left_metrics, right_metrics),
            }
        )
        totals_b = left_metrics if totals_b is None else _add_metrics(totals_b, left_metrics)
        totals_c = right_metrics if totals_c is None else _add_metrics(totals_c, right_metrics)
    assert totals_b is not None and totals_c is not None
    return TuningComparisonReport(
        schema_version=TUNING_COMPARISON_SCHEMA_VERSION,
        baseline_snapshot=baseline.snapshot.to_record(),
        candidate_snapshot=candidate.snapshot.to_record(),
        baseline_config=baseline.config.to_record(),
        candidate_config=candidate.config.to_record(),
        corpus=list(corpus),
        baseline_metrics=totals_b,
        candidate_metrics=totals_c,
        delta=_metric_delta(totals_b, totals_c),
        feedback_evidence=evidence.to_record(),
        data_quality={
            "snapshot_valid": True,
            "orphan_count": evidence.orphan_feedback_count,
            "orphan_feedback_count": evidence.orphan_feedback_count,
            "wrote_telemetry_jsonl": False,
            "wrote_feedback_jsonl": False,
        },
        per_fixture=per_fixture,
    )

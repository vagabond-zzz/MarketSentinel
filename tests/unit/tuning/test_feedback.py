from __future__ import annotations

from market_sentinel.telemetry.contract import (
    FeedbackLabel,
    SuppressionReason,
    TelemetryEvent,
    TelemetryKind,
    TelemetryName,
)
from market_sentinel.tuning.feedback import build_tuning_feedback_dataset


def _signal_row(name: TelemetryName, *, run_id: str, signal_id: str) -> dict[str, object]:
    extra: dict[str, object] = {}
    if name is TelemetryName.ALERT_SUPPRESSED:
        extra["suppression_reason"] = SuppressionReason.COOLDOWN
    return TelemetryEvent(
        telemetry_id=f"{run_id}-{signal_id}-{name.value}",
        name=name,
        kind=TelemetryKind.PIPELINE,
        created_timestamp=1.0,
        run_id=run_id,
        symbol="00700.HK",
        signal_id=signal_id,
        market_timestamp=1.0,
        family="tape",
        direction="up",
        priority="NOTICE",
        **extra,  # type: ignore[arg-type]
    ).to_record()


def _feedback(
    *,
    feedback_id: str,
    run_id: str,
    signal_id: str,
    label: str,
    created_timestamp: float,
) -> dict[str, object]:
    return {
        "feedback_id": feedback_id,
        "created_timestamp": created_timestamp,
        "run_id": run_id,
        "label": label,
        "signal_id": signal_id,
        "symbol": None,
        "event_id": None,
        "telemetry_id": None,
    }


def test_joinable_run_and_signal_is_eligible() -> None:
    telemetry = (_signal_row(TelemetryName.ALERT_CANDIDATE, run_id="run-a", signal_id="sig-1"),)
    feedback = (
        _feedback(
            feedback_id="f1",
            run_id="run-a",
            signal_id="sig-1",
            label=FeedbackLabel.USEFUL.value,
            created_timestamp=10.0,
        ),
    )
    dataset = build_tuning_feedback_dataset(feedback, telemetry)
    assert dataset.eligible_target_count == 1
    assert dataset.useful == 1
    assert dataset.orphan_feedback_count == 0


def test_unknown_signal_id_is_orphan() -> None:
    telemetry = (_signal_row(TelemetryName.ALERT_CANDIDATE, run_id="run-a", signal_id="known"),)
    feedback = (
        _feedback(
            feedback_id="f1",
            run_id="run-a",
            signal_id="unknown",
            label=FeedbackLabel.USEFUL.value,
            created_timestamp=10.0,
        ),
    )
    dataset = build_tuning_feedback_dataset(feedback, telemetry)
    assert dataset.eligible_target_count == 0
    assert dataset.orphan_feedback_count == 1
    assert dataset.useful == 0


def test_cross_run_same_signal_id_does_not_join() -> None:
    telemetry = (
        _signal_row(TelemetryName.SIGNAL_EPISODE_CREATED, run_id="run-a", signal_id="same"),
    )
    feedback = (
        _feedback(
            feedback_id="f1",
            run_id="run-b",
            signal_id="same",
            label=FeedbackLabel.TOO_NOISY.value,
            created_timestamp=10.0,
        ),
    )
    dataset = build_tuning_feedback_dataset(feedback, telemetry)
    assert dataset.eligible_target_count == 0
    assert dataset.orphan_feedback_count == 1


def test_invalid_feedback_is_not_eligible() -> None:
    telemetry = (_signal_row(TelemetryName.ALERT_SUPPRESSED, run_id="run-a", signal_id="sig-1"),)
    row = _feedback(
        feedback_id="f1",
        run_id="run-a",
        signal_id="sig-1",
        label="future_label",
        created_timestamp=10.0,
    )
    dataset = build_tuning_feedback_dataset((row,), telemetry)
    assert dataset.semantic_valid_feedback_count == 0
    assert dataset.eligible_target_count == 0
    missing = _feedback(
        feedback_id="f2",
        run_id="run-a",
        signal_id="sig-1",
        label=FeedbackLabel.USEFUL.value,
        created_timestamp=10.0,
    )
    del missing["run_id"]
    dataset = build_tuning_feedback_dataset((missing,), telemetry)
    assert dataset.semantic_valid_feedback_count == 0
    assert dataset.eligible_target_count == 0


def test_duplicate_feedback_latest_wins() -> None:
    telemetry = (_signal_row(TelemetryName.ALERT_CANDIDATE, run_id="run-a", signal_id="sig-1"),)
    feedback = (
        _feedback(
            feedback_id="f1",
            run_id="run-a",
            signal_id="sig-1",
            label=FeedbackLabel.USEFUL.value,
            created_timestamp=10.0,
        ),
        _feedback(
            feedback_id="f2",
            run_id="run-a",
            signal_id="sig-1",
            label=FeedbackLabel.TOO_NOISY.value,
            created_timestamp=11.0,
        ),
    )
    dataset = build_tuning_feedback_dataset(feedback, telemetry)
    assert dataset.raw_feedback_count == 2
    assert dataset.semantic_valid_feedback_count == 2
    assert dataset.eligible_target_count == 1
    assert dataset.superseded_feedback_count == 1
    assert dataset.too_noisy == 1
    assert dataset.useful == 0


def test_same_timestamp_uses_feedback_id_tie_break() -> None:
    telemetry = (_signal_row(TelemetryName.SIGNAL_ESCALATED, run_id="run-a", signal_id="sig-1"),)
    feedback = (
        _feedback(
            feedback_id="aaa",
            run_id="run-a",
            signal_id="sig-1",
            label=FeedbackLabel.USEFUL.value,
            created_timestamp=10.0,
        ),
        _feedback(
            feedback_id="bbb",
            run_id="run-a",
            signal_id="sig-1",
            label=FeedbackLabel.NOT_USEFUL.value,
            created_timestamp=10.0,
        ),
    )
    dataset = build_tuning_feedback_dataset(feedback, telemetry)
    assert dataset.eligible_target_count == 1
    assert dataset.not_useful == 1
    assert dataset.useful == 0
    assert dataset.superseded_feedback_count == 1


def test_no_feedback_is_not_negative() -> None:
    telemetry = (_signal_row(TelemetryName.ALERT_CANDIDATE, run_id="run-a", signal_id="sig-1"),)
    dataset = build_tuning_feedback_dataset((), telemetry)
    assert dataset.raw_feedback_count == 0
    assert dataset.eligible_target_count == 0
    assert dataset.not_useful == 0
    assert dataset.useful == 0
    assert dataset.too_noisy == 0
    assert dataset.too_late == 0


def test_user_feedback_alone_is_not_joinable_evidence() -> None:
    telemetry = (
        TelemetryEvent(
            telemetry_id="h1",
            name=TelemetryName.ALERT_PRESENTED,
            kind=TelemetryKind.HOST,
            created_timestamp=1.0,
            run_id="run-a",
            signal_id="only-host",
        ).to_record(),
    )
    feedback = (
        _feedback(
            feedback_id="f1",
            run_id="run-a",
            signal_id="only-host",
            label=FeedbackLabel.USEFUL.value,
            created_timestamp=10.0,
        ),
    )
    dataset = build_tuning_feedback_dataset(feedback, telemetry)
    assert dataset.orphan_feedback_count == 1
    assert dataset.eligible_target_count == 0

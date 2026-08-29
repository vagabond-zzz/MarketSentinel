from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from market_sentinel.evaluation.aggregate import _valid_feedback_row
from market_sentinel.telemetry.contract import FeedbackLabel, TelemetryName

JOINABLE_SIGNAL_EVIDENCE: frozenset[str] = frozenset(
    {
        TelemetryName.SIGNAL_EPISODE_CREATED.value,
        TelemetryName.SIGNAL_ESCALATED.value,
        TelemetryName.ALERT_CANDIDATE.value,
        TelemetryName.ALERT_SUPPRESSED.value,
    }
)

_LABELS = tuple(item.value for item in FeedbackLabel)


@dataclass(frozen=True)
class TuningFeedbackDataset:
    """Read-only eligible target-level feedback. Does not rewrite feedback.jsonl."""

    raw_feedback_count: int
    semantic_valid_feedback_count: int
    eligible_target_count: int
    orphan_feedback_count: int
    superseded_feedback_count: int
    useful: int
    not_useful: int
    too_noisy: int
    too_late: int

    def to_record(self) -> dict[str, Any]:
        return {
            "raw_feedback_count": self.raw_feedback_count,
            "semantic_valid_feedback_count": self.semantic_valid_feedback_count,
            "eligible_target_count": self.eligible_target_count,
            "orphan_feedback_count": self.orphan_feedback_count,
            "superseded_feedback_count": self.superseded_feedback_count,
            "useful": self.useful,
            "not_useful": self.not_useful,
            "too_noisy": self.too_noisy,
            "too_late": self.too_late,
        }


def _joinable_keys(telemetry: tuple[dict[str, object], ...]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for row in telemetry:
        if row.get("name") not in JOINABLE_SIGNAL_EVIDENCE:
            continue
        run_id = row.get("run_id")
        signal_id = row.get("signal_id")
        if not isinstance(run_id, str) or run_id.strip() == "":
            continue
        if not isinstance(signal_id, str) or signal_id.strip() == "":
            continue
        keys.add((run_id, signal_id))
    return keys


def _sort_key(row: dict[str, object]) -> tuple[float, str]:
    created = float(row["created_timestamp"])
    feedback_id = str(row["feedback_id"])
    return (created, feedback_id)


def build_tuning_feedback_dataset(
    feedback_rows: tuple[dict[str, object], ...] | list[dict[str, object]],
    telemetry_rows: tuple[dict[str, object], ...] | list[dict[str, object]],
) -> TuningFeedbackDataset:
    raw = list(feedback_rows)
    valid = [row for row in raw if _valid_feedback_row(row)]
    joinable = _joinable_keys(tuple(telemetry_rows))
    by_target: dict[tuple[str, str], list[dict[str, object]]] = {}
    orphan = 0
    for row in valid:
        key = (str(row["run_id"]), str(row["signal_id"]))
        if key not in joinable:
            orphan += 1
            continue
        by_target.setdefault(key, []).append(row)
    superseded = 0
    labels = {label: 0 for label in _LABELS}
    for rows in by_target.values():
        ordered = sorted(rows, key=_sort_key)
        superseded += len(ordered) - 1
        winner = ordered[-1]
        labels[str(winner["label"])] += 1
    return TuningFeedbackDataset(
        raw_feedback_count=len(raw),
        semantic_valid_feedback_count=len(valid),
        eligible_target_count=len(by_target),
        orphan_feedback_count=orphan,
        superseded_feedback_count=superseded,
        useful=labels[FeedbackLabel.USEFUL.value],
        not_useful=labels[FeedbackLabel.NOT_USEFUL.value],
        too_noisy=labels[FeedbackLabel.TOO_NOISY.value],
        too_late=labels[FeedbackLabel.TOO_LATE.value],
    )

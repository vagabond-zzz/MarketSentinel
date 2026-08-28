from __future__ import annotations

import math
from dataclasses import dataclass

from market_sentinel.telemetry.contract import TELEMETRY_DENYLIST, FeedbackLabel

USER_FEEDBACK_TYPE = "user_feedback"

_ALLOWED_KEYS = frozenset(
    {
        "protocol_version",
        "type",
        "request_id",
        "signal_id",
        "feedback_type",
        "created_timestamp",
    }
)


@dataclass(frozen=True)
class UserFeedbackFact:
    """Validated Protocol DTO. Not a UserFeedback storage record."""

    signal_id: str
    label: FeedbackLabel
    created_timestamp: float


def parse_user_feedback(command: dict[str, object]) -> UserFeedbackFact | str:
    """Validate a Protocol v1 user_feedback command. DTO ≠ storage record."""
    extra = set(command) - _ALLOWED_KEYS
    denied = extra & TELEMETRY_DENYLIST
    if denied:
        return f"denied keys: {sorted(denied)}"
    if extra:
        return f"unknown keys: {sorted(extra)}"
    raw_type = command.get("feedback_type")
    if not isinstance(raw_type, str):
        return "feedback_type is invalid"
    try:
        label = FeedbackLabel(raw_type)
    except ValueError:
        return "feedback_type is invalid"
    signal_id = command.get("signal_id")
    if not isinstance(signal_id, str) or signal_id.strip() == "":
        return "signal_id is required"
    created = command.get("created_timestamp")
    if created is None:
        return "created_timestamp is required"
    if isinstance(created, bool) or not isinstance(created, int | float):
        return "created_timestamp must be a finite number"
    if not math.isfinite(float(created)):
        return "created_timestamp must be a finite number"
    return UserFeedbackFact(
        signal_id=signal_id,
        label=label,
        created_timestamp=float(created),
    )

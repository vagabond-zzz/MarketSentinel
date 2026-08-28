from __future__ import annotations

import math
from dataclasses import dataclass

from market_sentinel.telemetry.contract import TELEMETRY_DENYLIST, TelemetryName

HOST_INTERACTION_TYPE = "host_interaction"

HOST_INTERACTION_ACTIONS: dict[str, TelemetryName] = {
    "alert_presented": TelemetryName.ALERT_PRESENTED,
    "alert_badge_reset": TelemetryName.ALERT_BADGE_RESET,
    "signal_opened": TelemetryName.SIGNAL_OPENED,
    "alert_dismissed": TelemetryName.ALERT_DISMISSED,
    "signal_muted": TelemetryName.SIGNAL_MUTED,
}

_ALLOWED_KEYS = frozenset(
    {
        "protocol_version",
        "type",
        "request_id",
        "action",
        "signal_id",
        "created_timestamp",
    }
)

_SIGNAL_REQUIRED = frozenset(
    {
        TelemetryName.ALERT_PRESENTED,
        TelemetryName.SIGNAL_OPENED,
        TelemetryName.ALERT_DISMISSED,
        TelemetryName.SIGNAL_MUTED,
    }
)

_HOST_ACTION = {
    TelemetryName.ALERT_PRESENTED: "presented",
    TelemetryName.ALERT_BADGE_RESET: "reset_unread",
    TelemetryName.SIGNAL_OPENED: "opened",
    TelemetryName.ALERT_DISMISSED: "dismissed",
    TelemetryName.SIGNAL_MUTED: "muted",
}


@dataclass(frozen=True)
class HostInteractionFact:
    name: TelemetryName
    created_timestamp: float | None
    signal_id: str | None
    host_action: str


def parse_host_interaction(command: dict[str, object]) -> HostInteractionFact | str:
    """Validate a Protocol v1 host_interaction command. DTO ≠ storage record."""
    extra = set(command) - _ALLOWED_KEYS
    denied = extra & TELEMETRY_DENYLIST
    if denied:
        return f"denied keys: {sorted(denied)}"
    if extra:
        return f"unknown keys: {sorted(extra)}"
    action = command.get("action")
    if not isinstance(action, str) or action not in HOST_INTERACTION_ACTIONS:
        return "action is invalid"
    name = HOST_INTERACTION_ACTIONS[action]
    created = command.get("created_timestamp")
    if created is not None:
        if isinstance(created, bool) or not isinstance(created, int | float):
            return "created_timestamp must be a finite number"
        if not math.isfinite(float(created)):
            return "created_timestamp must be a finite number"
    signal_id = command.get("signal_id")
    if signal_id is not None and (not isinstance(signal_id, str) or signal_id.strip() == ""):
        return "signal_id must be a non-empty string when present"
    if name in _SIGNAL_REQUIRED and not isinstance(signal_id, str):
        return f"{action} requires signal_id"
    if name is TelemetryName.ALERT_BADGE_RESET:
        signal_id = None
    return HostInteractionFact(
        name=name,
        created_timestamp=None if created is None else float(created),
        signal_id=signal_id if isinstance(signal_id, str) else None,
        host_action=_HOST_ACTION[name],
    )

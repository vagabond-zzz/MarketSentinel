from __future__ import annotations

import uuid
from collections.abc import Mapping

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events import thresholds as T


def rapid_move_severity(change_1m: float | None, change_5m: float | None) -> int | None:
    severity = 0
    if change_1m is not None:
        magnitude = abs(change_1m)
        if magnitude >= T.RAPID_1M_SEV4:
            severity = max(severity, 4)
        elif magnitude >= T.RAPID_1M_SEV3:
            severity = max(severity, 3)
        elif magnitude >= T.RAPID_1M_SEV2:
            severity = max(severity, 2)
    if change_5m is not None:
        magnitude = abs(change_5m)
        if magnitude >= T.RAPID_5M_SEV5:
            severity = max(severity, 5)
        elif magnitude >= T.RAPID_5M_SEV4:
            severity = max(severity, 4)
        elif magnitude >= T.RAPID_5M_SEV3:
            severity = max(severity, 3)
    return severity or None


def volume_spike_severity(ratio_1m: float | None, ratio_5m: float | None) -> int | None:
    severity = 0
    if ratio_5m is not None:
        if ratio_5m >= T.VOL_5M_SEV5:
            severity = max(severity, 5)
        elif ratio_5m >= T.VOL_5M_SEV4:
            severity = max(severity, 4)
        elif ratio_5m >= T.VOL_5M_SEV3:
            severity = max(severity, 3)
        elif ratio_5m >= T.VOL_5M_SEV2:
            severity = max(severity, 2)
    if ratio_1m is not None and ratio_1m >= T.VOL_1M_SEV3:
        severity = max(severity, 3)
    return severity or None


def move_direction(
    change_1m: float | None, change_5m: float | None, severity: int
) -> EventDirection:
    chosen: float | None = None
    if change_5m is not None and _five_minute_severity(abs(change_5m)) == severity:
        chosen = change_5m
    if change_1m is not None and _one_minute_severity(abs(change_1m)) == severity:
        chosen = change_1m
    if chosen is None:
        chosen = change_1m if change_1m is not None else change_5m
    if chosen is None or chosen == 0:
        return EventDirection.NONE
    return EventDirection.UP if chosen > 0 else EventDirection.DOWN


def _one_minute_severity(magnitude: float) -> int:
    if magnitude >= T.RAPID_1M_SEV4:
        return 4
    if magnitude >= T.RAPID_1M_SEV3:
        return 3
    if magnitude >= T.RAPID_1M_SEV2:
        return 2
    return 0


def _five_minute_severity(magnitude: float) -> int:
    if magnitude >= T.RAPID_5M_SEV5:
        return 5
    if magnitude >= T.RAPID_5M_SEV4:
        return 4
    if magnitude >= T.RAPID_5M_SEV3:
        return 3
    return 0


def breakout_severity(excess: float) -> int:
    if excess >= T.BREAKOUT_SEV5:
        return 5
    if excess >= T.BREAKOUT_SEV4:
        return 4
    return 3


def build_event(
    *,
    current: MarketFeatures,
    event_type: EventType,
    direction: EventDirection,
    severity: int,
    detected_at: float,
    metrics: Mapping[str, float | bool | None],
    ttl_s: float,
    rule_name: str,
) -> MarketEvent:
    return MarketEvent(
        id=uuid.uuid4().hex,
        symbol=current.symbol,
        type=event_type,
        direction=direction,
        severity=severity,
        market_timestamp=current.market_timestamp,
        received_timestamp=current.received_timestamp,
        detected_timestamp=detected_at,
        metrics=dict(metrics),
        dedupe_key=f"{current.symbol}|{event_type.value}|{direction.value}",
        ttl_s=ttl_s,
        rule_name=rule_name,
    )

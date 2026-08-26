from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from market_sentinel.domain.enums import EventDirection, EventType


@dataclass(frozen=True)
class MarketEvent:
    """Objective market fact. Copy and metrics must not include trade advice."""

    id: str
    symbol: str
    type: EventType
    direction: EventDirection
    severity: int
    market_timestamp: float
    received_timestamp: float
    detected_timestamp: float
    metrics: Mapping[str, float | bool | None]
    dedupe_key: str
    ttl_s: float
    rule_name: str

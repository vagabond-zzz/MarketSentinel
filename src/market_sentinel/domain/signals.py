from __future__ import annotations

from dataclasses import dataclass

from market_sentinel.domain.enums import GeneratedBy, SignalPriority
from market_sentinel.domain.features import MarketFeatures


@dataclass(frozen=True)
class Signal:
    """Rule-composed market fact. v0.2 has no host notification timestamp."""

    id: str
    event_ids: tuple[str, ...]
    symbol: str
    family: str
    priority: SignalPriority
    title: str
    summary: str
    generated_by: GeneratedBy
    market_timestamp: float
    received_timestamp: float
    detected_timestamp: float
    signal_created_timestamp: float
    expires_at: float | None = None


@dataclass(frozen=True)
class SignalTrace:
    signal_id: str
    event_ids: tuple[str, ...]
    rule_names: tuple[str, ...]
    features: MarketFeatures
    family: str
    priority: SignalPriority
    priority_reason: str
    detected_timestamp: float
    signal_created_timestamp: float

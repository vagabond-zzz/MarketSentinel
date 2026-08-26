from __future__ import annotations

from dataclasses import dataclass

from market_sentinel.domain.enums import EventDirection, GeneratedBy, SignalPriority
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures


@dataclass(frozen=True)
class Signal:
    """Rule-composed market fact for one directional episode. No notified_timestamp in v0.2."""

    id: str
    event_ids: tuple[str, ...]
    symbol: str
    family: str
    direction: EventDirection
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
    direction: EventDirection
    priority: SignalPriority
    priority_reason: str
    detected_timestamp: float
    signal_created_timestamp: float


@dataclass(frozen=True)
class SignalPipelineResult:
    """One Feature snapshot through detect → dedupe → compose → cooldown.

    ``alert_candidates`` are eligible Host reminders, not completed notifications.
    """

    accepted_events: tuple[MarketEvent, ...]
    signal_updates: tuple[Signal, ...]
    traces: tuple[SignalTrace, ...]
    alert_candidates: tuple[Signal, ...]

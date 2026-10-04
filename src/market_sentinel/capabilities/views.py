"""Read-only view models for capabilities that have no existing wire DTO.

Wire DTOs in ``ipc.dto`` stay the only representation of Protocol v1 state.
The views here fill two reported gaps without touching Protocol v1:

- feed health has no wire DTO (the daemon derives per-symbol status inside
  ``WireSymbolState``), so ``get_feed_health`` returns ``FeedHealthReport``;
- raw ``MarketEvent`` objects are not exposed over any wire (and carry rule
  internals: metrics, dedupe keys, TTL bookkeeping), so recent events are
  projected onto the narrower ``EventView``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from market_sentinel.domain.enums import EventDirection, EventType, FeedStatus
from market_sentinel.runtime.results import EngineTickResult

# Presentation-level severity for aggregate feed status. Mirrors the ordering
# in health.feed_health (private _WORST); duplicated here so capability reads
# can use the non-mutating peek_status() instead of status(), which updates a
# log-dedup bookkeeping field as a side effect.
_FEED_SEVERITY = {
    FeedStatus.LIVE: 0,
    FeedStatus.DELAYED: 1,
    FeedStatus.STALE: 2,
    FeedStatus.DISCONNECTED: 3,
}


@dataclass(frozen=True)
class SymbolFeedHealth:
    symbol: str
    status: str
    feed_latency_s: float | None
    last_update_age_s: float | None

    def to_wire(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status,
            "feed_latency_s": self.feed_latency_s,
            "last_update_age_s": self.last_update_age_s,
        }


@dataclass(frozen=True)
class FeedHealthReport:
    aggregate_status: str
    symbols: tuple[SymbolFeedHealth, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "aggregate_status": self.aggregate_status,
            "symbols": [item.to_wire() for item in self.symbols],
        }


@dataclass(frozen=True)
class EventView:
    """Read-only projection of a MarketEvent (facts only, no rule internals)."""

    id: str
    symbol: str
    event_type: str
    direction: str
    severity: int
    market_timestamp: float
    detected_timestamp: float
    rule_name: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "direction": self.direction,
            "severity": self.severity,
            "market_timestamp": self.market_timestamp,
            "detected_timestamp": self.detected_timestamp,
            "rule_name": self.rule_name,
        }


class RecentEventsBuffer:
    """Bounded store of recently accepted events, fed by the tick-loop owner.

    Core does not retain raw events beyond the tick (the signal composer keeps
    only what its cluster look-back needs), so a host that owns the tick loop
    publishes finished ticks via :meth:`observe_tick`. Hosts that never feed
    the buffer simply produce empty recent-events results.
    """

    def __init__(self, maxlen: int = 200) -> None:
        if maxlen < 1:
            raise ValueError("maxlen must be a positive integer")
        self._events: deque[EventView] = deque(maxlen=maxlen)

    def observe_tick(self, result: EngineTickResult) -> None:
        for symbol_result in result.symbol_results:
            for event in symbol_result.accepted_events:
                self._events.append(
                    EventView(
                        id=event.id,
                        symbol=event.symbol,
                        event_type=event.type.value
                        if isinstance(event.type, EventType)
                        else str(event.type),
                        direction=event.direction.value
                        if isinstance(event.direction, EventDirection)
                        else str(event.direction),
                        severity=event.severity,
                        market_timestamp=event.market_timestamp,
                        detected_timestamp=event.detected_timestamp,
                        rule_name=event.rule_name,
                    )
                )

    def recent(self, *, symbol: str | None = None, limit: int) -> tuple[EventView, ...]:
        rows = [item for item in self._events if symbol is None or item.symbol == symbol]
        return tuple(rows[-limit:])

    def __len__(self) -> int:
        return len(self._events)

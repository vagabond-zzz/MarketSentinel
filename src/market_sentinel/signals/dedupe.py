from __future__ import annotations

from dataclasses import dataclass

from market_sentinel.domain.events import MarketEvent


@dataclass
class _Record:
    market_timestamp: float
    severity: int
    ttl_s: float


class EventDeduper:
    """Suppress repeat events by symbol|type|direction using market-time TTL.

    Key has no Unix time bucket. Same or lower severity inside TTL is
    suppressed; a strictly higher severity upgrades; after TTL the key
    may emit again.
    """

    def __init__(self) -> None:
        self._records: dict[str, _Record] = {}

    def accept(self, event: MarketEvent) -> MarketEvent | None:
        previous = self._records.get(event.dedupe_key)
        if previous is None:
            self._store(event)
            return event
        elapsed = event.market_timestamp - previous.market_timestamp
        if elapsed < previous.ttl_s:
            if event.severity > previous.severity:
                self._store(event)
                return event
            return None
        self._store(event)
        return event

    def _store(self, event: MarketEvent) -> None:
        self._records[event.dedupe_key] = _Record(
            market_timestamp=event.market_timestamp,
            severity=event.severity,
            ttl_s=event.ttl_s,
        )

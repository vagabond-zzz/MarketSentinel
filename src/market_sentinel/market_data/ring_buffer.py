from __future__ import annotations

from bisect import bisect_left
from collections.abc import Sequence

from market_sentinel.domain.models import MarketSnapshot


class RingBuffer:
    def __init__(self, *, retention_s: float = 3600.0, max_size: int = 4096) -> None:
        if retention_s <= 0:
            raise ValueError("retention_s must be positive")
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self._retention_s = retention_s
        self._max_size = max_size
        self._items: list[MarketSnapshot] = []

    def append(self, snapshot: MarketSnapshot) -> None:
        timestamps = [item.market_timestamp for item in self._items]
        index = bisect_left(timestamps, snapshot.market_timestamp)
        if (
            index < len(self._items)
            and self._items[index].market_timestamp == snapshot.market_timestamp
        ):
            self._items[index] = snapshot
        else:
            self._items.insert(index, snapshot)
        self._evict()

    def latest(self) -> MarketSnapshot | None:
        if not self._items:
            return None
        return self._items[-1]

    def window(self, duration_s: float) -> Sequence[MarketSnapshot]:
        latest = self.latest()
        if latest is None:
            return ()
        return self.since(latest.market_timestamp - duration_s)

    def since(self, timestamp: float) -> Sequence[MarketSnapshot]:
        return tuple(item for item in self._items if item.market_timestamp >= timestamp)

    def _evict(self) -> None:
        newest = self._items[-1].market_timestamp
        cutoff = newest - self._retention_s
        while self._items and self._items[0].market_timestamp < cutoff:
            del self._items[0]
        overflow = len(self._items) - self._max_size
        if overflow > 0:
            del self._items[:overflow]

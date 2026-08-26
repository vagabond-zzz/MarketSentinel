from __future__ import annotations

from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.market_data.ring_buffer import RingBuffer


class SymbolBuffers:
    def __init__(self, *, retention_s: float = 3600.0, max_size: int = 4096) -> None:
        self._retention_s = retention_s
        self._max_size = max_size
        self._buffers: dict[str, RingBuffer] = {}

    def append(self, snapshot: MarketSnapshot) -> None:
        self._buffer_for(snapshot.symbol).append(snapshot)

    def latest(self, symbol: str) -> MarketSnapshot | None:
        buffer = self._buffers.get(symbol)
        if buffer is None:
            return None
        return buffer.latest()

    def at_or_before(self, symbol: str, timestamp: float) -> MarketSnapshot | None:
        buffer = self._buffers.get(symbol)
        if buffer is None:
            return None
        return buffer.at_or_before(timestamp)

    def window(self, symbol: str, duration_s: float):
        return self._buffer_for(symbol).window(duration_s)

    def since(self, symbol: str, timestamp: float):
        return self._buffer_for(symbol).since(timestamp)

    def _buffer_for(self, symbol: str) -> RingBuffer:
        buffer = self._buffers.get(symbol)
        if buffer is None:
            buffer = RingBuffer(retention_s=self._retention_s, max_size=self._max_size)
            self._buffers[symbol] = buffer
        return buffer

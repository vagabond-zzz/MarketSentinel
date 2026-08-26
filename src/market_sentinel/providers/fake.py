from __future__ import annotations

from typing import Any

from market_sentinel.clock import Clock
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.errors import SnapshotValidationError
from market_sentinel.market_data.normalizer import normalize_snapshot


class FakeProvider:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._quotes: dict[str, dict[str, Any]] = {}
        self._failed: set[str] = set()
        self._timeout = False
        self.last_requested: list[str] = []

    def set_quote(self, symbol: str, **fields: Any) -> None:
        quote = _default_quote(symbol, self._clock.wall_time())
        quote.update(fields)
        quote["symbol"] = symbol
        self._quotes[symbol] = quote

    def fail_symbol(self, symbol: str) -> None:
        self._failed.add(symbol)

    def set_timeout(self, timeout: bool) -> None:
        self._timeout = timeout

    async def fetch_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        self.last_requested = list(symbols)
        if self._timeout:
            raise TimeoutError("provider timeout")

        snapshots: list[MarketSnapshot] = []
        for symbol in symbols:
            if symbol in self._failed:
                continue
            raw = self._quotes.get(symbol) or _default_quote(symbol, self._clock.wall_time())
            try:
                snapshots.append(normalize_snapshot(raw, self._clock))
            except SnapshotValidationError:
                continue
        return snapshots


def _default_quote(symbol: str, market_timestamp: float) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "price": 100.0,
        "open": 100.0,
        "high": 100.0,
        "low": 100.0,
        "prev_close": 100.0,
        "volume": 0.0,
        "turnover": None,
        "market_timestamp": market_timestamp,
    }

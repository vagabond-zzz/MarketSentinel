from __future__ import annotations

import json
from pathlib import Path

from market_sentinel.domain.models import WatchItem
from market_sentinel.errors import WatchlistFullError, WatchlistSymbolError

_DEFAULT_LIMIT = 10


class Watchlist:
    def __init__(self, path: Path, *, limit: int = _DEFAULT_LIMIT) -> None:
        self._path = path
        self._limit = limit
        self._items: dict[str, WatchItem] = {}
        self._load()

    def add(self, symbol: str) -> WatchItem:
        existing = self._items.get(symbol)
        if existing is not None:
            return existing
        if len(self._items) >= self._limit:
            raise WatchlistFullError(f"watchlist limit is {self._limit}")
        item = WatchItem(symbol=symbol, enabled=True)
        self._items[symbol] = item
        self._save()
        return item

    def remove(self, symbol: str) -> None:
        self._require(symbol)
        del self._items[symbol]
        self._save()

    def list(self) -> list[WatchItem]:
        return list(self._items.values())

    def enable(self, symbol: str) -> WatchItem:
        return self._set_enabled(symbol, True)

    def disable(self, symbol: str) -> WatchItem:
        return self._set_enabled(symbol, False)

    def enabled_symbols(self) -> list[str]:
        return [item.symbol for item in self._items.values() if item.enabled]

    def _set_enabled(self, symbol: str, enabled: bool) -> WatchItem:
        item = self._require(symbol)
        updated = WatchItem(symbol=item.symbol, enabled=enabled)
        self._items[symbol] = updated
        self._save()
        return updated

    def _require(self, symbol: str) -> WatchItem:
        item = self._items.get(symbol)
        if item is None:
            raise WatchlistSymbolError(f"unknown symbol: {symbol}")
        return item

    def _load(self) -> None:
        if not self._path.exists():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        for raw in payload.get("items", []):
            symbol = str(raw["symbol"])
            self._items[symbol] = WatchItem(symbol=symbol, enabled=bool(raw.get("enabled", True)))

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "items": [
                {"symbol": item.symbol, "enabled": item.enabled} for item in self._items.values()
            ]
        }
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

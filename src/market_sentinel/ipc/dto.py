from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WireSignal:
    id: str
    family: str
    direction: str
    priority: str
    title: str
    summary: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "direction": self.direction,
            "priority": self.priority,
            "title": self.title,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class WireSymbolState:
    symbol: str
    price: float | None
    scheduler_level: str
    feed_status: str
    change_1m: float | None
    change_5m: float | None
    change_15m: float | None
    volume_ratio_1m: float | None
    volume_ratio_5m: float | None
    ema5: float | None
    ema20: float | None
    rsi14: float | None
    vwap: float | None
    active_signals: tuple[WireSignal, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "scheduler_level": self.scheduler_level,
            "feed_status": self.feed_status,
            "change_1m": self.change_1m,
            "change_5m": self.change_5m,
            "change_15m": self.change_15m,
            "volume_ratio_1m": self.volume_ratio_1m,
            "volume_ratio_5m": self.volume_ratio_5m,
            "ema5": self.ema5,
            "ema20": self.ema20,
            "rsi14": self.rsi14,
            "vwap": self.vwap,
            "active_signals": [item.to_wire() for item in self.active_signals],
        }


@dataclass(frozen=True)
class WireMarketState:
    watchlist_count: int
    feed_status: str
    symbols: tuple[WireSymbolState, ...]

    def to_wire(self) -> dict[str, Any]:
        return {
            "watchlist_count": self.watchlist_count,
            "feed_status": self.feed_status,
            "symbols": [item.to_wire() for item in self.symbols],
        }


@dataclass(frozen=True)
class WireAlertCandidate:
    id: str
    symbol: str
    family: str
    direction: str
    priority: str
    title: str
    summary: str

    def to_wire(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "family": self.family,
            "direction": self.direction,
            "priority": self.priority,
            "title": self.title,
            "summary": self.summary,
        }

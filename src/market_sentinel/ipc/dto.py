from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WireIntelligence:
    status: str
    summary: str | None = None
    reason: str | None = None
    confidence: float | None = None
    fallback_reason: str | None = None
    worth_highlight: bool | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": self.status}
        if self.summary is not None:
            payload["summary"] = self.summary
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.fallback_reason is not None:
            payload["fallback_reason"] = self.fallback_reason
        if self.worth_highlight is not None:
            payload["worth_highlight"] = self.worth_highlight
        return payload


@dataclass(frozen=True)
class WireSignal:
    id: str
    family: str
    direction: str
    priority: str
    title: str
    summary: str
    intelligence: WireIntelligence | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "family": self.family,
            "direction": self.direction,
            "priority": self.priority,
            "title": self.title,
            "summary": self.summary,
        }
        if self.intelligence is not None:
            payload["intelligence"] = self.intelligence.to_wire()
        return payload


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
    change_day: float | None = None
    above_vwap: bool | None = None
    session_high_obs: float | None = None
    session_low_obs: float | None = None
    session_high_ref: float | None = None
    session_low_ref: float | None = None
    market_timestamp: float | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
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
        if self.change_day is not None:
            payload["change_day"] = self.change_day
        if self.above_vwap is not None:
            payload["above_vwap"] = self.above_vwap
        if self.session_high_obs is not None:
            payload["session_high_obs"] = self.session_high_obs
        if self.session_low_obs is not None:
            payload["session_low_obs"] = self.session_low_obs
        if self.session_high_ref is not None:
            payload["session_high_ref"] = self.session_high_ref
        if self.session_low_ref is not None:
            payload["session_low_ref"] = self.session_low_ref
        if self.market_timestamp is not None:
            payload["market_timestamp"] = self.market_timestamp
        return payload


@dataclass(frozen=True)
class WireMarketState:
    watchlist_count: int
    feed_status: str
    symbols: tuple[WireSymbolState, ...]
    intelligence_enabled: bool = False
    replay_complete: bool = False
    last_market_timestamp: float | None = None

    def to_wire(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "watchlist_count": self.watchlist_count,
            "feed_status": self.feed_status,
            "symbols": [item.to_wire() for item in self.symbols],
        }
        if self.intelligence_enabled:
            payload["intelligence_enabled"] = True
        if self.replay_complete:
            payload["replay_complete"] = True
        if self.last_market_timestamp is not None:
            payload["last_market_timestamp"] = self.last_market_timestamp
        return payload


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

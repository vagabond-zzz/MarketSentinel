from __future__ import annotations

from dataclasses import dataclass

from market_sentinel.domain.enums import FeedStatus, SchedulerLevel


@dataclass(frozen=True)
class MarketSnapshot:
    """Normalized quote.

    ``volume`` is session-cumulative share/lot count from session open through
    ``market_timestamp``. ``turnover``, when present, is session-cumulative
    notional in the same session. Feature code must not treat these as
    per-sample interval values.
    """

    symbol: str
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: float
    turnover: float | None
    market_timestamp: float
    received_timestamp: float


@dataclass(frozen=True)
class WatchItem:
    symbol: str
    enabled: bool = True


@dataclass(frozen=True)
class MarketState:
    symbol: str
    latest: MarketSnapshot | None
    level: SchedulerLevel
    feed_status: FeedStatus
    feed_latency: float | None
    last_update_age: float | None

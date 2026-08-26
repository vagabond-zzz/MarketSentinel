from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeaturePolicy:
    """Shared feature-layer knobs. Rolling windows also require same-session + freshness."""

    max_anchor_lag_s: float = 30.0
    volume_ratio_lookback: int = 20
    bar_seconds: float = 60.0


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    start_timestamp: float
    end_timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float | None


@dataclass(frozen=True)
class MarketFeatures:
    symbol: str
    market_timestamp: float
    received_timestamp: float
    change_1m: float | None
    change_5m: float | None
    change_15m: float | None
    change_day: float | None
    day_range_position: float | None
    volume_1m: float | None
    volume_5m: float | None
    volume_ratio_1m: float | None
    volume_ratio_5m: float | None
    vwap: float | None
    above_vwap: bool | None
    ema5: float | None
    ema20: float | None
    rsi14: float | None
    session_high_ref: float | None
    session_low_ref: float | None

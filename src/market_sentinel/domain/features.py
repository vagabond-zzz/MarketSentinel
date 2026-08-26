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
    """Sampled / observed 1-minute OHLC from polled snapshots.

    Adaptive polling (1s / 3s / 10s) means this bar is the aggregation of
    snapshots the process actually saw. It is **not** guaranteed to equal an
    exchange-published 1-minute K-line.

    ``volume`` / ``turnover`` are interval increments derived from session
    cumulative snapshot fields. They are ``None`` unless a reliable same-session
    previous-minute cumulative anchor exists. A missing baseline (mid-session
    start) or an unattributable gap must not be filled with the cumulative
    value or a guessed interval.

    Intraday breakout rules must use provider session extremes
    (``max(price, snapshot.high)`` / ``min(price, snapshot.low)``) against
    previous ``session_high_ref`` / ``session_low_ref``, not this sampled
    bar high / low.
    """

    symbol: str
    start_timestamp: float
    end_timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    turnover: float | None


@dataclass(frozen=True)
class MarketFeatures:
    """Per-symbol feature snapshot at one market timestamp.

    ``change_*`` values are **decimal fractions**, not percent points:

    - ``0.006`` = 0.6%
    - ``0.01``  = 1%
    - ``0.035`` = 3.5%

    Event-rule thresholds must use the same unit (``0.006``, never ``0.6``
    to mean 0.6%).

    ``session_high_ref`` / ``session_low_ref`` are previous same-session
    provider extremes. Breakout detection compares those refs with the
    current provider-observed session extreme, not sampled ``MarketBar``
    high / low.
    """

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

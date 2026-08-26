from __future__ import annotations

from market_sentinel.domain.models import MarketSnapshot


def ema(closes: list[float], *, period: int) -> float | None:
    if period <= 0 or len(closes) < period:
        return None
    seed = sum(closes[:period]) / period
    k = 2.0 / (period + 1)
    value = seed
    for close in closes[period:]:
        value = close * k + value * (1.0 - k)
    return value


def rsi_wilder(closes: list[float], *, period: int = 14) -> float | None:
    if period <= 0 or len(closes) < period + 1:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=False):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def session_vwap(snapshot: MarketSnapshot) -> tuple[float | None, bool | None]:
    if snapshot.turnover is None or snapshot.volume <= 0:
        return (None, None)
    vwap = snapshot.turnover / snapshot.volume
    return (vwap, snapshot.price > vwap)

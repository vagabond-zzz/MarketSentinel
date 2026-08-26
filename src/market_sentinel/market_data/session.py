from __future__ import annotations

from datetime import datetime, timedelta, timezone

from market_sentinel.domain.models import MarketSnapshot

_SESSION_TZ = timezone(timedelta(hours=8))


def session_id(market_timestamp: float) -> str:
    """UTC+8 calendar date used as the v0.2 session key for A/H names."""
    return datetime.fromtimestamp(market_timestamp, tz=_SESSION_TZ).date().isoformat()


def is_same_session(left_ts: float, right_ts: float) -> bool:
    return session_id(left_ts) == session_id(right_ts)


def session_extreme_high(snapshot: MarketSnapshot) -> float:
    """Session high implied by this snapshot: max(price, snapshot.high)."""
    return max(snapshot.price, snapshot.high)


def session_extreme_low(snapshot: MarketSnapshot) -> float:
    """Session low implied by this snapshot: min(price, snapshot.low)."""
    return min(snapshot.price, snapshot.low)

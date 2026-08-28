from __future__ import annotations

import math
from datetime import datetime, time, timedelta, timezone

from market_sentinel.domain.models import MarketSnapshot

_SESSION_TZ = timezone(timedelta(hours=8))

# A-share cash session (UTC+8). Lunch and overnight do not count as market hours.
_CASH_WINDOWS: tuple[tuple[time, time], ...] = (
    (time(9, 30), time(11, 30)),
    (time(13, 0), time(15, 0)),
)


def session_id(market_timestamp: float) -> str:
    """UTC+8 calendar date used as the v0.2 session key for A/H names."""
    return datetime.fromtimestamp(market_timestamp, tz=_SESSION_TZ).date().isoformat()


def is_same_session(left_ts: float, right_ts: float) -> bool:
    return session_id(left_ts) == session_id(right_ts)


def is_a_share_symbol(symbol: str) -> bool:
    """A-share market-hour metric supports SH/SZ only. HK/other is not this calendar."""
    return symbol.endswith(".SH") or symbol.endswith(".SZ")


def cash_session_overlap_s(start_ts: float, end_ts: float) -> float:
    """Elapsed A-share cash-session seconds between two market timestamps.

    Windows are 09:30–11:30 and 13:00–15:00 UTC+8 on weekdays. Saturday and
    Sunday contribute 0. Equal timestamps yield 0 (do not extrapolate from one
    point). Official exchange holidays are not calendar-aware.
    """
    if not math.isfinite(start_ts) or not math.isfinite(end_ts):
        return 0.0
    if end_ts < start_ts:
        start_ts, end_ts = end_ts, start_ts
    if start_ts == end_ts:
        return 0.0
    start = datetime.fromtimestamp(start_ts, tz=_SESSION_TZ)
    end = datetime.fromtimestamp(end_ts, tz=_SESSION_TZ)
    total = 0.0
    day = start.date()
    last = end.date()
    while day <= last:
        if day.weekday() < 5:
            for win_start, win_end in _CASH_WINDOWS:
                window_start = datetime.combine(day, win_start, tzinfo=_SESSION_TZ)
                window_end = datetime.combine(day, win_end, tzinfo=_SESSION_TZ)
                left = max(start, window_start)
                right = min(end, window_end)
                if right > left:
                    total += (right - left).total_seconds()
        day += timedelta(days=1)
    return total


def session_extreme_high(snapshot: MarketSnapshot) -> float:
    """Session high implied by this snapshot: max(price, snapshot.high)."""
    return max(snapshot.price, snapshot.high)


def session_extreme_low(snapshot: MarketSnapshot) -> float:
    """Session low implied by this snapshot: min(price, snapshot.low)."""
    return min(snapshot.price, snapshot.low)

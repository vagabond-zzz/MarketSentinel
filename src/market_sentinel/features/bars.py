from __future__ import annotations

import math
from collections.abc import Sequence

from market_sentinel.domain.features import MarketBar
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.market_data.session import is_same_session


def completed_minute_bars(
    snapshots: Sequence[MarketSnapshot],
    *,
    latest_ts: float,
    bar_seconds: float = 60.0,
) -> list[MarketBar]:
    """Build completed sampled minute bars for the current session.

    Volume/turnover are interval deltas only when the previous completed
    minute is contiguous in the same session, so the previous bar's last
    cumulative snapshot is a reliable baseline. The first observed bar and
    any bar after a gap return ``None`` for those fields.
    """
    if not snapshots or bar_seconds <= 0:
        return []
    forming_start = math.floor(latest_ts / bar_seconds) * bar_seconds
    buckets: dict[float, list[MarketSnapshot]] = {}
    for snapshot in snapshots:
        if not is_same_session(snapshot.market_timestamp, latest_ts):
            continue
        start = math.floor(snapshot.market_timestamp / bar_seconds) * bar_seconds
        if start >= forming_start:
            continue
        buckets.setdefault(start, []).append(snapshot)

    bars: list[MarketBar] = []
    prev_end: float | None = None
    last_volume: float | None = None
    last_turnover: float | None = None
    for start in sorted(buckets):
        group = sorted(buckets[start], key=lambda item: item.market_timestamp)
        last = group[-1]
        prices = [item.price for item in group]
        contiguous = prev_end is not None and start == prev_end
        volume = _interval_delta(last.volume, last_volume, contiguous)
        turnover = _interval_delta(last.turnover, last_turnover, contiguous)
        bars.append(
            MarketBar(
                symbol=last.symbol,
                start_timestamp=start,
                end_timestamp=start + bar_seconds,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=volume,
                turnover=turnover,
            )
        )
        last_volume = last.volume
        last_turnover = last.turnover
        prev_end = start + bar_seconds
    return bars


def _interval_delta(
    current: float | None,
    previous: float | None,
    contiguous: bool,
) -> float | None:
    if not contiguous or current is None or previous is None:
        return None
    return max(0.0, current - previous)

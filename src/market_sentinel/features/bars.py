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
    last_volume = 0.0
    last_turnover: float | None = None
    for start in sorted(buckets):
        group = sorted(buckets[start], key=lambda item: item.market_timestamp)
        last = group[-1]
        prices = [item.price for item in group]
        bar_volume = max(0.0, last.volume - last_volume)
        last_volume = last.volume
        bar_turnover = None
        if last.turnover is not None:
            prev_turnover = last_turnover or 0.0
            bar_turnover = max(0.0, last.turnover - prev_turnover)
            last_turnover = last.turnover
        bars.append(
            MarketBar(
                symbol=last.symbol,
                start_timestamp=start,
                end_timestamp=start + bar_seconds,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=bar_volume,
                turnover=bar_turnover,
            )
        )
    return bars

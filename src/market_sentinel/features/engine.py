from __future__ import annotations

from market_sentinel.domain.features import FeaturePolicy, MarketFeatures
from market_sentinel.features.bars import completed_minute_bars
from market_sentinel.features.indicators import ema, rsi_wilder, session_vwap
from market_sentinel.features.rolling import price_change, volume_delta, volume_ratio
from market_sentinel.market_data.ring_buffer import RingBuffer
from market_sentinel.market_data.session import (
    is_same_session,
    session_extreme_high,
    session_extreme_low,
)

# Opening-period volume ratios stay None until 20 in-session 1-minute samples exist.
# v0.2 does not use a previous-day intraday volume profile.


class FeatureEngine:
    def __init__(self, policy: FeaturePolicy | None = None) -> None:
        self._policy = policy or FeaturePolicy()

    def compute(self, buffer: RingBuffer) -> MarketFeatures | None:
        latest = buffer.latest()
        if latest is None:
            return None
        high_ref, low_ref = _session_refs(buffer, latest)
        # Day range uses provider session extremes, not sampled bar OHLC.
        high_now = (
            session_extreme_high(latest)
            if high_ref is None
            else max(high_ref, session_extreme_high(latest))
        )
        low_now = (
            session_extreme_low(latest)
            if low_ref is None
            else min(low_ref, session_extreme_low(latest))
        )
        day_range = None
        if high_now > low_now:
            day_range = (latest.price - low_now) / (high_now - low_now)
        day_change = None
        if latest.prev_close != 0:
            day_change = (latest.price - latest.prev_close) / latest.prev_close
        session_snaps = [
            snapshot
            for snapshot in buffer.since(0.0)
            if is_same_session(snapshot.market_timestamp, latest.market_timestamp)
        ]
        bars = completed_minute_bars(
            session_snaps,
            latest_ts=latest.market_timestamp,
            bar_seconds=self._policy.bar_seconds,
        )
        closes = [bar.close for bar in bars]
        vwap, above_vwap = session_vwap(latest)
        return MarketFeatures(
            symbol=latest.symbol,
            market_timestamp=latest.market_timestamp,
            received_timestamp=latest.received_timestamp,
            change_1m=price_change(buffer, latest, 60.0, self._policy),
            change_5m=price_change(buffer, latest, 300.0, self._policy),
            change_15m=price_change(buffer, latest, 900.0, self._policy),
            change_day=day_change,
            day_range_position=day_range,
            volume_1m=volume_delta(buffer, latest, 60.0, self._policy),
            volume_5m=volume_delta(buffer, latest, 300.0, self._policy),
            volume_ratio_1m=volume_ratio(buffer, latest, 60.0, self._policy),
            volume_ratio_5m=volume_ratio(buffer, latest, 300.0, self._policy),
            vwap=vwap,
            above_vwap=above_vwap,
            ema5=ema(closes, period=5),
            ema20=ema(closes, period=20),
            rsi14=rsi_wilder(closes, period=14),
            session_high_ref=high_ref,
            session_low_ref=low_ref,
        )


def _session_refs(buffer: RingBuffer, latest) -> tuple[float | None, float | None]:
    high_ref: float | None = None
    low_ref: float | None = None
    for snapshot in buffer.since(0.0):
        if snapshot.market_timestamp >= latest.market_timestamp:
            continue
        if not is_same_session(snapshot.market_timestamp, latest.market_timestamp):
            continue
        high = session_extreme_high(snapshot)
        low = session_extreme_low(snapshot)
        high_ref = high if high_ref is None else max(high_ref, high)
        low_ref = low if low_ref is None else min(low_ref, low)
    return high_ref, low_ref

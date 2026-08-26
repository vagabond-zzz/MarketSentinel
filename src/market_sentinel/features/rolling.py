from __future__ import annotations

from market_sentinel.domain.features import FeaturePolicy
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.market_data.ring_buffer import RingBuffer
from market_sentinel.market_data.session import is_same_session


def resolve_anchor(
    buffer: RingBuffer,
    latest: MarketSnapshot,
    window_s: float,
    max_anchor_lag_s: float,
) -> MarketSnapshot | None:
    t_ref = latest.market_timestamp - window_s
    if not is_same_session(t_ref, latest.market_timestamp):
        return None
    anchor = buffer.at_or_before(t_ref)
    if anchor is None:
        return None
    if not is_same_session(anchor.market_timestamp, latest.market_timestamp):
        return None
    if t_ref - anchor.market_timestamp > max_anchor_lag_s:
        return None
    return anchor


def price_change(
    buffer: RingBuffer,
    latest: MarketSnapshot,
    window_s: float,
    policy: FeaturePolicy,
) -> float | None:
    anchor = resolve_anchor(buffer, latest, window_s, policy.max_anchor_lag_s)
    if anchor is None or anchor.price == 0:
        return None
    return (latest.price - anchor.price) / anchor.price  # decimal fraction; 0.006 = 0.6%


def volume_delta(
    buffer: RingBuffer,
    latest: MarketSnapshot,
    window_s: float,
    policy: FeaturePolicy,
) -> float | None:
    anchor = resolve_anchor(buffer, latest, window_s, policy.max_anchor_lag_s)
    if anchor is None:
        return None
    return max(0.0, latest.volume - anchor.volume)


def volume_ratio(
    buffer: RingBuffer,
    latest: MarketSnapshot,
    window_s: float,
    policy: FeaturePolicy,
) -> float | None:
    current = volume_delta(buffer, latest, window_s, policy)
    if current is None:
        return None
    samples = _historical_volume_deltas(buffer, latest, window_s, policy)
    if samples is None:
        return None
    baseline = sum(samples) / len(samples)
    if baseline <= 0:
        return None
    return current / baseline


def snapshot_as_of(
    buffer: RingBuffer,
    timestamp: float,
    latest: MarketSnapshot,
    max_anchor_lag_s: float,
) -> MarketSnapshot | None:
    found = buffer.at_or_before(timestamp)
    if found is None:
        return None
    if not is_same_session(found.market_timestamp, latest.market_timestamp):
        return None
    if timestamp - found.market_timestamp > max_anchor_lag_s:
        return None
    return found


def _historical_volume_deltas(
    buffer: RingBuffer,
    latest: MarketSnapshot,
    window_s: float,
    policy: FeaturePolicy,
) -> list[float] | None:
    samples: list[float] = []
    for step in range(1, policy.volume_ratio_lookback + 1):
        as_of_ts = latest.market_timestamp - step * 60.0
        as_of = snapshot_as_of(buffer, as_of_ts, latest, policy.max_anchor_lag_s)
        if as_of is None:
            return None
        delta = volume_delta(buffer, as_of, window_s, policy)
        if delta is None:
            return None
        samples.append(delta)
    return samples

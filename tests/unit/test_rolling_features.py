from datetime import datetime, timedelta, timezone

from market_sentinel.domain.features import FeaturePolicy
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.features.engine import FeatureEngine
from market_sentinel.market_data.ring_buffer import RingBuffer

CST = timezone(timedelta(hours=8))
OPEN = datetime(2024, 1, 15, 9, 30, tzinfo=CST).timestamp()
AFTERNOON = datetime(2024, 1, 15, 13, 0, tzinfo=CST).timestamp()
NEXT_OPEN = datetime(2024, 1, 16, 9, 30, tzinfo=CST).timestamp()


def _snap(
    ts: float,
    price: float,
    volume: float,
    *,
    high: float | None = None,
    low: float | None = None,
    prev_close: float = 100.0,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="00700.HK",
        price=price,
        open=100.0,
        high=price if high is None else high,
        low=price if low is None else low,
        prev_close=prev_close,
        volume=volume,
        turnover=None,
        market_timestamp=ts,
        received_timestamp=ts,
    )


def _buffer(rows: list[MarketSnapshot]) -> RingBuffer:
    buffer = RingBuffer(retention_s=7200.0, max_size=4096)
    for row in rows:
        buffer.append(row)
    return buffer


def _engine() -> FeatureEngine:
    return FeatureEngine(FeaturePolicy(max_anchor_lag_s=30.0, volume_ratio_lookback=20))


def test_one_minute_change_uses_same_session_fresh_anchor() -> None:
    rows = [
        _snap(OPEN + offset, 100.0 + offset / 60.0, volume=1000.0 + offset)
        for offset in range(0, 80, 10)
    ]
    features = _engine().compute(_buffer(rows))
    assert features is not None
    latest = rows[-1]
    anchor_price = 100.0 + 10.0 / 60.0  # ts = OPEN+10, T_ref = OPEN+70-60 = OPEN+10
    expected = (latest.price - anchor_price) / anchor_price
    assert features.change_1m == expected
    assert features.change_day == (latest.price - 100.0) / 100.0


def test_change_is_none_when_history_is_short() -> None:
    features = _engine().compute(_buffer([_snap(OPEN, 100.0, 0.0)]))
    assert features is not None
    assert features.change_1m is None
    assert features.change_5m is None
    assert features.change_15m is None
    assert features.volume_1m is None
    assert features.volume_ratio_1m is None


def test_lunch_gap_does_not_reuse_morning_anchor() -> None:
    morning = [_snap(OPEN + 10.0, 100.0, 5_000.0), _snap(OPEN + 20.0, 101.0, 5_100.0)]
    afternoon = [_snap(AFTERNOON, 102.0, 5_200.0), _snap(AFTERNOON + 10.0, 103.0, 5_300.0)]
    features = _engine().compute(_buffer(morning + afternoon))
    assert features is not None
    assert features.change_1m is None
    assert features.change_5m is None
    assert features.volume_1m is None


def test_volume_delta_does_not_cross_session() -> None:
    yesterday = _snap(OPEN - 24 * 3600.0, 99.0, 1_000_000.0)
    today = _snap(NEXT_OPEN, 100.0, 2_000.0)
    today_later = _snap(NEXT_OPEN + 10.0, 101.0, 2_100.0)
    features = _engine().compute(_buffer([yesterday, today, today_later]))
    assert features is not None
    assert features.volume_1m is None
    assert features.change_1m is None


def test_stale_anchor_beyond_max_lag_is_none() -> None:
    rows = [
        _snap(OPEN, 100.0, 1_000.0),
        _snap(OPEN + 50.0, 101.0, 1_100.0),  # T_ref for 1m at OPEN+50 is OPEN-10; no
        _snap(OPEN + 80.0, 102.0, 1_200.0),
    ]
    # latest OPEN+80, T_ref=OPEN+20, at_or_before -> OPEN (lag 20s) wait OPEN+20-OPEN=20 <= 30
    # Need lag > 30: latest OPEN+100, T_ref=OPEN+40, only snap at OPEN (lag 40s)
    rows = [_snap(OPEN, 100.0, 1_000.0), _snap(OPEN + 100.0, 102.0, 1_200.0)]
    features = _engine().compute(_buffer(rows))
    assert features is not None
    assert features.change_1m is None
    assert features.volume_1m is None


def test_volume_ratio_is_none_before_baseline_warmup() -> None:
    rows = [
        _snap(OPEN + minute * 60.0 + 50.0, 100.0, 1000.0 + minute * 10.0) for minute in range(10)
    ]
    features = _engine().compute(_buffer(rows))
    assert features is not None
    assert features.volume_ratio_1m is None
    assert features.volume_ratio_5m is None


def test_volume_ratio_after_twenty_in_session_minute_samples() -> None:
    rows: list[MarketSnapshot] = []
    volume = 0.0
    for second in range(0, 26 * 60 + 1, 10):
        volume += 10.0
        rows.append(_snap(OPEN + second, 100.0, volume))
    features = _engine().compute(_buffer(rows))
    assert features is not None
    assert features.volume_1m == 60.0  # 6 samples * 10 volume increment in 60s
    assert features.volume_ratio_1m == 1.0
    assert features.volume_ratio_5m == 1.0


def test_session_high_ref_is_previous_extreme_not_current() -> None:
    rows = [
        _snap(OPEN, 100.0, 1.0, high=101.0, low=99.0),
        _snap(OPEN + 10.0, 103.0, 2.0, high=102.0, low=100.0),
    ]
    features = _engine().compute(_buffer(rows))
    assert features is not None
    assert features.session_high_ref == 101.0
    assert features.session_low_ref == 99.0
    assert features.day_range_position == (103.0 - 99.0) / (103.0 - 99.0)

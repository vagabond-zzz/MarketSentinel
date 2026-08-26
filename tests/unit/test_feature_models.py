from datetime import datetime, timedelta, timezone

from market_sentinel.domain.features import FeaturePolicy, MarketBar, MarketFeatures
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.ring_buffer import RingBuffer
from market_sentinel.market_data.session import (
    is_same_session,
    session_extreme_high,
    session_extreme_low,
    session_id,
)


def _snapshot(ts: float, price: float = 100.0, volume: float = 1.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="00700.HK",
        price=price,
        open=100.0,
        high=max(100.0, price),
        low=min(100.0, price),
        prev_close=100.0,
        volume=volume,
        turnover=None,
        market_timestamp=ts,
        received_timestamp=ts,
    )


def test_at_or_before_returns_latest_snapshot_not_after_timestamp() -> None:
    buffer = RingBuffer(retention_s=3600.0, max_size=50)
    buffer.append(_snapshot(10.0, 100.0))
    buffer.append(_snapshot(20.0, 110.0))
    buffer.append(_snapshot(30.0, 120.0))
    found = buffer.at_or_before(20.0)
    assert found is not None
    assert found.market_timestamp == 20.0
    assert found.price == 110.0
    before = buffer.at_or_before(19.9)
    assert before is not None
    assert before.market_timestamp == 10.0
    assert buffer.at_or_before(9.9) is None


def test_symbol_buffers_at_or_before_is_per_symbol() -> None:
    buffers = SymbolBuffers(retention_s=3600.0, max_size=50)
    buffers.append(_snapshot(10.0, 600.0))
    found = buffers.at_or_before("00700.HK", 10.0)
    assert found is not None
    assert found.price == 600.0
    assert buffers.at_or_before("600519.SH", 10.0) is None


def test_session_id_uses_utc_plus_eight_calendar_day() -> None:
    cst = timezone(timedelta(hours=8))
    morning = datetime(2024, 1, 15, 0, 30, tzinfo=cst).timestamp()
    night = datetime(2024, 1, 15, 23, 30, tzinfo=cst).timestamp()
    next_day = datetime(2024, 1, 16, 0, 30, tzinfo=cst).timestamp()
    assert session_id(morning) == "2024-01-15"
    assert session_id(night) == "2024-01-15"
    assert is_same_session(morning, night)
    assert not is_same_session(night, next_day)


def test_session_extremes_use_price_and_snapshot_high_low() -> None:
    snapshot = MarketSnapshot(
        symbol="600519.SH",
        price=100.0,
        open=99.0,
        high=105.0,
        low=90.0,
        prev_close=98.0,
        volume=10.0,
        turnover=None,
        market_timestamp=1.0,
        received_timestamp=1.0,
    )
    assert session_extreme_high(snapshot) == 105.0
    assert session_extreme_low(snapshot) == 90.0
    spiked = MarketSnapshot(
        symbol="600519.SH",
        price=110.0,
        open=99.0,
        high=105.0,
        low=90.0,
        prev_close=98.0,
        volume=10.0,
        turnover=None,
        market_timestamp=2.0,
        received_timestamp=2.0,
    )
    assert session_extreme_high(spiked) == 110.0
    assert session_extreme_low(spiked) == 90.0


def test_feature_models_exist_with_optional_metrics() -> None:
    policy = FeaturePolicy()
    assert policy.max_anchor_lag_s == 30.0
    assert policy.volume_ratio_lookback == 20
    features = MarketFeatures(
        symbol="00700.HK",
        market_timestamp=1.0,
        received_timestamp=1.0,
        change_1m=None,
        change_5m=None,
        change_15m=None,
        change_day=None,
        day_range_position=None,
        volume_1m=None,
        volume_5m=None,
        volume_ratio_1m=None,
        volume_ratio_5m=None,
        vwap=None,
        above_vwap=None,
        ema5=None,
        ema20=None,
        rsi14=None,
        session_high_ref=None,
        session_low_ref=None,
        session_high_obs=100.0,
        session_low_obs=100.0,
    )
    assert features.change_1m is None
    documented = MarketFeatures(
        symbol="00700.HK",
        market_timestamp=1.0,
        received_timestamp=1.0,
        change_1m=0.006,
        change_5m=0.01,
        change_15m=0.035,
        change_day=None,
        day_range_position=None,
        volume_1m=None,
        volume_5m=None,
        volume_ratio_1m=None,
        volume_ratio_5m=None,
        vwap=None,
        above_vwap=None,
        ema5=None,
        ema20=None,
        rsi14=None,
        session_high_ref=None,
        session_low_ref=None,
        session_high_obs=100.0,
        session_low_obs=100.0,
    )
    assert documented.change_1m == 0.006  # 0.6%, not 0.6 percent-points
    assert documented.change_5m == 0.01
    assert documented.change_15m == 0.035
    bar = MarketBar(
        symbol="00700.HK",
        start_timestamp=0.0,
        end_timestamp=60.0,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        turnover=None,
    )
    assert bar.close == 100.5

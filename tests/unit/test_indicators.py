from datetime import datetime, timedelta, timezone

import pytest

from market_sentinel.domain.features import FeaturePolicy
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.features.bars import completed_minute_bars
from market_sentinel.features.engine import FeatureEngine
from market_sentinel.features.indicators import ema, rsi_wilder, session_vwap
from market_sentinel.market_data.ring_buffer import RingBuffer

CST = timezone(timedelta(hours=8))
OPEN = datetime(2024, 1, 15, 9, 30, tzinfo=CST).timestamp()
BASE = OPEN - (OPEN % 60)


def _snap(
    ts: float,
    price: float,
    volume: float,
    *,
    turnover: float | None = None,
) -> MarketSnapshot:
    return MarketSnapshot(
        symbol="00700.HK",
        price=price,
        open=100.0,
        high=price,
        low=price,
        prev_close=100.0,
        volume=volume,
        turnover=turnover,
        market_timestamp=ts,
        received_timestamp=ts,
    )


def _buffer(rows: list[MarketSnapshot]) -> RingBuffer:
    buffer = RingBuffer(retention_s=7200.0, max_size=4096)
    for row in rows:
        buffer.append(row)
    return buffer


def test_completed_minute_bars_exclude_forming_minute_and_use_cumulative_delta() -> None:
    rows = [
        _snap(BASE, 100.0, 100.0),
        _snap(BASE + 30.0, 102.0, 130.0),
        _snap(BASE + 60.0, 101.0, 160.0),
        _snap(BASE + 90.0, 103.0, 200.0),
    ]
    bars = completed_minute_bars(rows, latest_ts=BASE + 90.0, bar_seconds=60.0)
    assert len(bars) == 1
    bar = bars[0]
    assert bar.start_timestamp == BASE
    assert bar.end_timestamp == BASE + 60.0
    assert bar.open == 100.0
    assert bar.high == 102.0
    assert bar.low == 100.0
    assert bar.close == 102.0
    assert bar.volume is None
    assert bar.turnover is None


def test_second_contiguous_bar_uses_previous_cumulative_anchor() -> None:
    rows = [
        _snap(BASE, 100.0, 100.0, turnover=10_000.0),
        _snap(BASE + 30.0, 102.0, 130.0, turnover=13_000.0),
        _snap(BASE + 60.0, 101.0, 160.0, turnover=16_000.0),
        _snap(BASE + 90.0, 103.0, 200.0, turnover=20_000.0),
        _snap(BASE + 150.0, 104.0, 210.0, turnover=21_000.0),
    ]
    bars = completed_minute_bars(rows, latest_ts=BASE + 150.0, bar_seconds=60.0)
    assert len(bars) == 2
    assert bars[0].volume is None
    assert bars[0].turnover is None
    assert bars[1].volume == 70.0
    assert bars[1].turnover == 7_000.0


def test_mid_session_start_does_not_treat_cumulative_as_first_bar_volume() -> None:
    rows = [
        _snap(BASE + 600.0, 100.0, 50_000.0, turnover=5_000_000.0),
        _snap(BASE + 630.0, 101.0, 50_080.0, turnover=5_008_000.0),
        _snap(BASE + 660.0, 102.0, 50_150.0, turnover=5_015_000.0),
        _snap(BASE + 720.0, 103.0, 50_200.0, turnover=5_020_000.0),
    ]
    bars = completed_minute_bars(rows, latest_ts=BASE + 720.0, bar_seconds=60.0)
    assert len(bars) == 2
    assert bars[0].close == 101.0
    assert bars[0].volume is None
    assert bars[1].volume == 70.0
    assert bars[1].turnover == 7_000.0


def test_gapped_minute_does_not_attribute_delta_to_a_single_bar() -> None:
    rows = [
        _snap(BASE, 100.0, 100.0),
        _snap(BASE + 30.0, 101.0, 130.0),
        _snap(BASE + 240.0, 110.0, 800.0),
        _snap(BASE + 270.0, 111.0, 820.0),
        _snap(BASE + 300.0, 112.0, 830.0),
    ]
    bars = completed_minute_bars(rows, latest_ts=BASE + 300.0, bar_seconds=60.0)
    starts = [bar.start_timestamp for bar in bars]
    assert BASE in starts
    assert BASE + 240.0 in starts
    by_start = {bar.start_timestamp: bar for bar in bars}
    assert by_start[BASE].volume is None
    assert by_start[BASE + 240.0].volume is None


def test_completed_minute_bars_ignore_other_session_snapshots() -> None:
    previous_day = BASE - 24 * 3600.0
    rows = [
        _snap(previous_day, 90.0, 9_000.0),
        _snap(BASE, 100.0, 100.0),
        _snap(BASE + 30.0, 101.0, 130.0),
        _snap(BASE + 90.0, 102.0, 160.0),
    ]
    bars = completed_minute_bars(rows, latest_ts=BASE + 90.0, bar_seconds=60.0)
    assert len(bars) == 1
    assert bars[0].start_timestamp == BASE
    assert bars[0].volume is None


def test_ema_seeds_with_sma_then_applies_standard_k() -> None:
    assert ema([1.0, 2.0, 3.0, 4.0, 5.0], period=5) == 3.0
    # k = 2/6, next close 6 -> 6*(1/3) + 3*(2/3) = 4
    assert ema([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], period=5) == 4.0
    assert ema([1.0, 2.0, 3.0, 4.0], period=5) is None


def test_wilder_rsi_warmup_and_all_gains() -> None:
    rising = [float(i) for i in range(1, 16)]
    rsi = rsi_wilder(rising, period=14)
    assert rsi == 100.0
    assert rsi_wilder(rising[:14], period=14) is None


def test_wilder_rsi_flat_series_is_fifty() -> None:
    assert rsi_wilder([50.0] * 15, period=14) == 50.0


def test_wilder_rsi_all_losses_is_zero() -> None:
    falling = [float(i) for i in range(15, 0, -1)]
    assert rsi_wilder(falling, period=14) == 0.0


def test_wilder_rsi_classic_seed_example() -> None:
    closes = [
        100.0,
        101.0,
        102.0,
        103.0,
        104.0,
        105.0,
        104.0,
        103.0,
        102.0,
        101.0,
        100.0,
        101.0,
        102.0,
        103.0,
        104.0,
    ]
    # 14 changes: nine +1 and five -1 -> avg_gain=9/14, avg_loss=5/14, RSI=64.2857...
    assert rsi_wilder(closes, period=14) == pytest.approx(64.285714, abs=1e-6)


def test_vwap_requires_session_turnover() -> None:
    snap = _snap(BASE, 10.0, 100.0, turnover=None)
    assert session_vwap(snap) == (None, None)
    snap = _snap(BASE, 12.0, 100.0, turnover=1000.0)
    assert session_vwap(snap) == (10.0, True)


def test_feature_engine_fills_indicators_after_warmup() -> None:
    rows: list[MarketSnapshot] = []
    volume = 0.0
    for minute in range(25):
        volume += 50.0
        price = 100.0 + minute
        rows.append(
            _snap(
                OPEN + minute * 60.0,
                price,
                volume,
                turnover=volume * 100.0,
            )
        )
    rows.append(
        _snap(OPEN + 24 * 60.0 + 10.0, 124.5, volume + 5.0, turnover=(volume + 5.0) * 100.0)
    )
    features = FeatureEngine(FeaturePolicy()).compute(_buffer(rows))
    assert features is not None
    assert features.ema5 is not None
    assert features.ema20 is not None
    assert features.rsi14 == 100.0
    assert features.vwap == 100.0
    assert features.above_vwap is True

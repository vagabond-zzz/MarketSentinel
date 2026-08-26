import time
from datetime import datetime, timedelta, timezone

from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.features.engine import FeatureEngine
from market_sentinel.market_data.ring_buffer import RingBuffer

CST = timezone(timedelta(hours=8))
OPEN = datetime(2024, 1, 15, 9, 30, tzinfo=CST).timestamp()
SYMBOLS = [
    "600519.SH",
    "000001.SZ",
    "601318.SH",
    "000858.SZ",
    "601398.SH",
    "00700.HK",
    "00941.HK",
    "01299.HK",
    "02318.HK",
    "03690.HK",
]


def _fill(symbol: str) -> RingBuffer:
    buffer = RingBuffer(retention_s=7200.0, max_size=4096)
    volume = 0.0
    for step in range(120):
        volume += 10.0
        ts = OPEN + step * 10.0
        buffer.append(
            MarketSnapshot(
                symbol=symbol,
                price=100.0 + step * 0.01,
                open=100.0,
                high=100.0 + step * 0.01,
                low=100.0,
                prev_close=100.0,
                volume=volume,
                turnover=volume * 100.0,
                market_timestamp=ts,
                received_timestamp=ts,
            )
        )
    return buffer


def test_ten_symbol_feature_compute_stays_under_one_second() -> None:
    engine = FeatureEngine()
    buffers = [_fill(symbol) for symbol in SYMBOLS]
    started = time.perf_counter()
    features = [engine.compute(buffer) for buffer in buffers]
    elapsed = time.perf_counter() - started
    assert all(item is not None for item in features)
    assert elapsed < 1.0
    print(f"\n10-symbol feature compute: {elapsed * 1000:.2f} ms")

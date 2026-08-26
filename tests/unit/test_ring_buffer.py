from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.ring_buffer import RingBuffer
from market_sentinel.market_data.state import MarketStateStore


def _snapshot(symbol: str, ts: float, price: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        price=price,
        open=100.0,
        high=max(100.0, price),
        low=min(100.0, price),
        prev_close=100.0,
        volume=1.0,
        turnover=None,
        market_timestamp=ts,
        received_timestamp=ts,
    )


def test_append_and_latest() -> None:
    buffer = RingBuffer(retention_s=60.0, max_size=10)
    buffer.append(_snapshot("00700.HK", 10.0, 100.0))
    buffer.append(_snapshot("00700.HK", 11.0, 101.0))
    latest = buffer.latest()
    assert latest is not None
    assert latest.price == 101.0
    assert latest.market_timestamp == 11.0


def test_window_and_since_include_boundary() -> None:
    buffer = RingBuffer(retention_s=3600.0, max_size=50)
    for ts, price in ((10.0, 100.0), (12.0, 101.0), (15.0, 102.0)):
        buffer.append(_snapshot("00700.HK", ts, price))
    window = buffer.window(5.0)
    assert [item.market_timestamp for item in window] == [10.0, 12.0, 15.0]
    since = buffer.since(12.0)
    assert [item.market_timestamp for item in since] == [12.0, 15.0]


def test_out_of_order_insert_keeps_time_order() -> None:
    buffer = RingBuffer(retention_s=3600.0, max_size=50)
    buffer.append(_snapshot("00700.HK", 20.0, 120.0))
    buffer.append(_snapshot("00700.HK", 10.0, 110.0))
    buffer.append(_snapshot("00700.HK", 15.0, 115.0))
    assert [item.market_timestamp for item in buffer.since(0.0)] == [10.0, 15.0, 20.0]
    latest = buffer.latest()
    assert latest is not None
    assert latest.market_timestamp == 20.0
    assert latest.price == 120.0


def test_duplicate_timestamp_replaces() -> None:
    buffer = RingBuffer(retention_s=3600.0, max_size=50)
    buffer.append(_snapshot("00700.HK", 10.0, 100.0))
    buffer.append(_snapshot("00700.HK", 10.0, 105.0))
    assert len(buffer.since(0.0)) == 1
    latest = buffer.latest()
    assert latest is not None
    assert latest.price == 105.0


def test_retention_drops_old_snapshots() -> None:
    buffer = RingBuffer(retention_s=10.0, max_size=50)
    buffer.append(_snapshot("00700.HK", 0.0, 90.0))
    buffer.append(_snapshot("00700.HK", 5.0, 95.0))
    buffer.append(_snapshot("00700.HK", 11.0, 100.0))
    assert [item.market_timestamp for item in buffer.since(0.0)] == [5.0, 11.0]


def test_max_size_evicts_oldest() -> None:
    buffer = RingBuffer(retention_s=3600.0, max_size=3)
    for ts in (1.0, 2.0, 3.0, 4.0):
        buffer.append(_snapshot("00700.HK", ts, 100.0 + ts))
    assert [item.market_timestamp for item in buffer.since(0.0)] == [2.0, 3.0, 4.0]


def test_symbol_buffers_are_independent() -> None:
    buffers = SymbolBuffers(retention_s=3600.0, max_size=50)
    buffers.append(_snapshot("00700.HK", 1.0, 600.0))
    buffers.append(_snapshot("600519.SH", 1.0, 1480.0))
    hk = buffers.latest("00700.HK")
    sh = buffers.latest("600519.SH")
    assert hk is not None and hk.price == 600.0
    assert sh is not None and sh.price == 1480.0


def test_market_state_store_keeps_latest_snapshot() -> None:
    store = MarketStateStore()
    first = _snapshot("00700.HK", 1.0, 600.0)
    second = _snapshot("00700.HK", 2.0, 602.5)
    store.update_latest(first)
    state = store.update_latest(second)
    stored = store.get("00700.HK")
    assert state.latest is second
    assert stored is not None
    assert stored.latest is second


def test_symbol_buffers_exposes_ring_buffer() -> None:
    buffers = SymbolBuffers()
    buffers.append(_snapshot("00700.HK", 1.0, 600.0))
    buffer = buffers.buffer("00700.HK")
    assert buffer is not None
    assert buffer.latest() is not None
    assert buffers.buffer("600519.SH") is None

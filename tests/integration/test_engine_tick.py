from pathlib import Path

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import FeedStatus
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist

TEN_SYMBOLS = [
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


def _engine(tmp_path: Path) -> tuple[FakeClock, FakeProvider, MarketEngine, SymbolBuffers]:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    for symbol in TEN_SYMBOLS:
        watchlist.add(symbol)
    provider = FakeProvider(clock)
    buffers = SymbolBuffers(retention_s=3600.0, max_size=3)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=buffers,
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    return clock, provider, engine, buffers


@pytest.mark.integration
async def test_tick_cycle_disable_disconnect_and_recovery(tmp_path: Path) -> None:
    clock, provider, engine, buffers = _engine(tmp_path)

    await engine.tick()
    assert provider.last_requested == TEN_SYMBOLS
    assert all(buffers.latest(symbol) is not None for symbol in TEN_SYMBOLS)

    engine.watchlist.disable(TEN_SYMBOLS[0])
    clock.advance(10.0)
    provider.last_requested = []
    await engine.tick()
    assert TEN_SYMBOLS[0] not in provider.last_requested
    assert set(provider.last_requested) == set(TEN_SYMBOLS[1:])

    provider.set_timeout(True)
    for _ in range(3):
        clock.advance(10.0)
        await engine.tick()
    assert engine.health.status(TEN_SYMBOLS[1]) is FeedStatus.DISCONNECTED

    provider.set_timeout(False)
    clock.advance(10.0)
    await engine.tick()
    assert engine.health.status(TEN_SYMBOLS[1]) is FeedStatus.LIVE

    for _ in range(8):
        clock.advance(10.0)
        await engine.tick()
    assert len(buffers.since(TEN_SYMBOLS[1], 0.0)) <= 3
    assert clock.monotonic_time() == 130.0

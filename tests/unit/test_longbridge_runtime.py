from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import FeedStatus
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


def _quote(symbol: str, *, price: float, ts: float) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        last_done=price,
        open=price,
        high=price + 1.0,
        low=price - 1.0,
        prev_close=price,
        volume=100.0,
        turnover=10_000.0,
        timestamp=ts,
        trade_status=0,
    )


async def test_longbridge_valid_quote_reaches_features(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    market_ts = clock.wall_time() - 0.2

    def quote_fn(symbols: list[str]) -> list[SimpleNamespace]:
        return [_quote(symbol, price=100.0, ts=market_ts) for symbol in symbols]

    engine = MarketEngine(
        clock=clock,
        watchlist=Watchlist(tmp_path / "watchlist.json"),
        provider=LongbridgeQuoteProvider(clock, quote_fn=quote_fn),
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    engine.watchlist.add("600519.SH")
    result = await engine.tick()
    row = result.for_symbol("600519.SH")
    assert row is not None
    assert row.features is not None
    state = engine.states.get("600519.SH")
    assert state is not None
    assert state.feed_status is FeedStatus.LIVE
    assert state.latest is not None
    assert state.latest.turnover is None
    assert state.latest.received_timestamp == clock.wall_time()


async def test_longbridge_timeout_degrades_health_without_events(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    market_ts = clock.wall_time() - 0.2
    fail = {"on": False}

    def quote_fn(symbols: list[str]) -> list[SimpleNamespace]:
        if fail["on"]:
            raise TimeoutError("slow")
        return [_quote(symbol, price=100.0, ts=market_ts) for symbol in symbols]

    engine = MarketEngine(
        clock=clock,
        watchlist=Watchlist(tmp_path / "watchlist.json"),
        provider=LongbridgeQuoteProvider(clock, quote_fn=quote_fn, timeout_s=8.0),
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    engine.watchlist.add("000001.SZ")
    await engine.tick()
    fail["on"] = True
    for _ in range(3):
        clock.advance(10.0)
        result = await engine.tick()
    row = result.for_symbol("000001.SZ")
    assert row is not None
    assert row.accepted_events == ()
    assert row.alert_candidates == ()
    assert engine.health.status("000001.SZ") is FeedStatus.DISCONNECTED

from pathlib import Path

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


def _engine(
    tmp_path: Path, clock: FakeClock | None = None
) -> tuple[FakeClock, FakeProvider, MarketEngine]:
    clock = clock or FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    provider = FakeProvider(clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    return clock, provider, engine


async def test_tick_fetches_enabled_symbols_and_updates_state(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    engine.watchlist.add("600519.SH")
    engine.watchlist.disable("600519.SH")
    provider.set_quote(
        "00700.HK",
        price=602.5,
        prev_close=595.0,
        market_timestamp=clock.wall_time() - 0.2,
    )
    await engine.tick()
    assert provider.last_requested == ["00700.HK"]
    latest = engine.buffers.latest("00700.HK")
    assert latest is not None
    assert latest.price == 602.5
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.feed_status is FeedStatus.LIVE
    assert state.level is SchedulerLevel.COLD
    assert engine.buffers.latest("600519.SH") is None
    assert clock.monotonic_time() == 0.0


async def test_tick_timeout_is_not_disconnected(tmp_path: Path) -> None:
    _, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    provider.set_timeout(True)
    await engine.tick()
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.feed_status is not FeedStatus.DISCONNECTED


async def test_second_tick_waits_for_interval(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await engine.tick()
    assert engine.scheduler.next_wait_s(["00700.HK"]) == 10.0
    provider.last_requested = []
    await engine.tick()
    assert provider.last_requested == []
    clock.advance_monotonic(10.0)
    await engine.tick()
    assert provider.last_requested == ["00700.HK"]

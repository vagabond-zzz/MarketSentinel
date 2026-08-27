from __future__ import annotations

import asyncio
import io
import time

from tests.unit.ipc.helpers import command, parse_stdout
from tests.unit.ipc.test_daemon import BlockingStdin, _drain

from market_sentinel.clock import FakeClock
from market_sentinel.domain.models import MarketSnapshot, WatchItem
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.ipc.daemon import MarketDaemon
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.normalizer import normalize_snapshot
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


class GateProvider:
    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.fetch_started = asyncio.Event()
        self.release = asyncio.Event()
        self.requested: list[list[str]] = []

    async def fetch_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        self.requested.append(list(symbols))
        self.fetch_started.set()
        await self.release.wait()
        snapshots: list[MarketSnapshot] = []
        for symbol in symbols:
            snapshots.append(
                normalize_snapshot(
                    {
                        "symbol": symbol,
                        "price": 100.0,
                        "open": 100.0,
                        "high": 100.0,
                        "low": 100.0,
                        "prev_close": 100.0,
                        "volume": 0.0,
                        "turnover": None,
                        "market_timestamp": self._clock.wall_time(),
                    },
                    self._clock,
                )
            )
        return snapshots


async def test_set_watchlist_waits_for_in_flight_tick_then_applies() -> None:
    clock = FakeClock()
    provider = GateProvider(clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=Watchlist(persist=False),
        provider=provider,
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(
                cold_interval_s=0.01,
                warm_interval_s=0.01,
                hot_interval_s=0.01,
                hot_downgrade_dwell_s=0.0,
                warm_downgrade_dwell_s=0.0,
            ),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    engine.watchlist.replace([WatchItem("AAA.HK", True)])
    stdin = BlockingStdin()
    stdout = io.StringIO()
    daemon = MarketDaemon(engine, stdin=stdin, stdout=stdout)
    task = asyncio.create_task(daemon.run())
    stdin.push(command("hello", "h1"))
    await _drain(stdout, 1)
    stdin.push(command("start", "s1"))
    await asyncio.wait_for(provider.fetch_started.wait(), timeout=5)
    assert provider.requested[0] == ["AAA.HK"]

    stdin.push(command("set_watchlist", "w1", items=[{"symbol": "BBB.HK", "enabled": True}]))
    await asyncio.sleep(0.05)
    assert engine.watchlist.enabled_symbols() == ["AAA.HK"]

    provider.release.set()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        messages = parse_stdout(stdout.getvalue())
        if any(item.get("request_id") == "w1" and item["type"] == "ack" for item in messages):
            break
        await asyncio.sleep(0.01)
    else:
        raise TimeoutError(stdout.getvalue())

    assert engine.watchlist.enabled_symbols() == ["BBB.HK"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if any(req == ["BBB.HK"] for req in provider.requested):
            break
        await asyncio.sleep(0.01)
    else:
        raise TimeoutError(f"never fetched BBB: {provider.requested}")

    for requested in provider.requested:
        assert requested in (["AAA.HK"], ["BBB.HK"])
        assert requested != ["AAA.HK", "BBB.HK"]

    stdin.push(command("shutdown", "x"))
    await asyncio.wait_for(task, timeout=5)

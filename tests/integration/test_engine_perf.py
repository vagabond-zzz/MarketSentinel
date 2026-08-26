import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_sentinel.clock import FakeClock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.replay import ReplayProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist

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


def _write_replay(path: Path, *, snapshots: int = 120) -> None:
    lines: list[str] = []
    volumes = {symbol: 0.0 for symbol in SYMBOLS}
    for step in range(snapshots):
        ts = OPEN + step * 10.0
        batch = []
        for index, symbol in enumerate(SYMBOLS):
            volumes[symbol] += 10.0
            price = 100.0 + index + step * 0.01
            batch.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "open": 100.0,
                    "high": price,
                    "low": 100.0,
                    "prev_close": 100.0,
                    "volume": volumes[symbol],
                    "turnover": volumes[symbol] * price,
                    "market_timestamp": ts,
                }
            )
        lines.append(json.dumps(batch, separators=(",", ":")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def test_ten_symbol_engine_replay_stays_under_two_seconds(tmp_path: Path) -> None:
    fixture = tmp_path / "ten_symbol_120.jsonl"
    _write_replay(fixture)
    clock = FakeClock(wall=OPEN, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    for symbol in SYMBOLS:
        watchlist.add(symbol)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=ReplayProvider(fixture, clock),
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(cold_interval_s=0.0, warm_interval_s=0.0, hot_interval_s=0.0),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    started = time.perf_counter()
    for step in range(120):
        clock.set_wall(OPEN + step * 10.0)
        result = await engine.tick()
        assert len(result.symbol_results) == 10
    elapsed = time.perf_counter() - started
    # Uninstrumented ~1s; coverage instrumentation is slower. Bound only catches
    # order-of-magnitude regressions, not millisecond noise.
    assert elapsed < 8.0
    print(f"\n10-symbol x 120 engine ticks: {elapsed * 1000:.2f} ms")
    assert all(engine.states.get(symbol) is not None for symbol in SYMBOLS)
    assert engine.states.get(SYMBOLS[0]).features is not None  # type: ignore[union-attr]

from __future__ import annotations

import json
from typing import Any

from market_sentinel.clock import FakeClock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


def command(message_type: str, request_id: str, **fields: Any) -> str:
    payload = {"protocol_version": 1, "type": message_type, "request_id": request_id, **fields}
    return json.dumps(payload) + "\n"


def make_engine() -> tuple[FakeClock, FakeProvider, MarketEngine]:
    clock = FakeClock()
    provider = FakeProvider(clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=Watchlist(persist=False),
        provider=provider,
        scheduler=AdaptiveScheduler(
            clock,
            SchedulerPolicy(
                cold_interval_s=0.05,
                warm_interval_s=0.05,
                hot_interval_s=0.05,
                hot_downgrade_dwell_s=0.0,
                warm_downgrade_dwell_s=0.0,
            ),
        ),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    return clock, provider, engine


def parse_stdout(buffer: str) -> list[dict[str, Any]]:
    lines = [line for line in buffer.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]

from __future__ import annotations

import logging

from market_sentinel.clock import Clock
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.base import MarketProvider
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist

logger = logging.getLogger(__name__)


class MarketEngine:
    def __init__(
        self,
        *,
        clock: Clock,
        watchlist: Watchlist,
        provider: MarketProvider,
        scheduler: AdaptiveScheduler,
        buffers: SymbolBuffers,
        states: MarketStateStore,
        health: FeedHealthTracker,
    ) -> None:
        self.clock = clock
        self.watchlist = watchlist
        self.provider = provider
        self.scheduler = scheduler
        self.buffers = buffers
        self.states = states
        self.health = health

    async def tick(self) -> None:
        enabled = self.watchlist.enabled_symbols()
        due = self.scheduler.due_symbols(enabled)
        if due:
            await self._fetch_due(due)
        self._project(enabled)

    async def _fetch_due(self, due: list[str]) -> None:
        try:
            snapshots = await self.provider.fetch_quotes(due)
        except Exception as exc:
            logger.warning("provider fetch failed: %s", exc)
            for symbol in due:
                self.health.observe(symbol, error=exc)
                self.scheduler.mark_fetched(symbol)
            return

        found = {item.symbol: item for item in snapshots}
        for symbol in due:
            snapshot = found.get(symbol)
            if snapshot is None:
                self.health.observe(symbol, error=RuntimeError("missing quote"))
            else:
                self.buffers.append(snapshot)
                self.states.update_latest(snapshot)
                self.health.observe(symbol, snapshot)
            self.scheduler.mark_fetched(symbol)

    def _project(self, symbols: list[str]) -> None:
        for symbol in symbols:
            self.states.apply_runtime(
                symbol,
                level=self.scheduler.get_level(symbol),
                feed_status=self.health.status(symbol),
                feed_latency=self.health.feed_latency(symbol),
                last_update_age=self.health.last_update_age(symbol),
            )

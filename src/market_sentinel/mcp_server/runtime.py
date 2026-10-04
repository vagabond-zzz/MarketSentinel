"""Standalone Core runtime for the MCP server process.

Deliberately standalone: this runtime never attaches to a Cursor daemon,
never speaks Protocol v1, and writes no telemetry by default. It owns one
MarketEngine plus its tick loop, and exposes read-only capabilities to the
MCP layer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from market_sentinel.capabilities import MarketCapabilities
from market_sentinel.clock import Clock, SystemClock
from market_sentinel.errors import MarketSentinelError, ProviderError
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.intelligence.bootstrap import optional_intelligence
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.normalizer import is_valid_symbol
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.factory import create_provider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.telemetry.runtime import TelemetryRuntime
from market_sentinel.watchlist.watchlist import Watchlist

logger = logging.getLogger(__name__)

PROVIDER_CHOICES = ("fake", "replay", "longbridge")
DEFAULT_FAKE_SYMBOLS = ("600519.SH", "000001.SZ", "300750.SZ")


class McpConfigError(MarketSentinelError):
    """MCP standalone runtime configuration is invalid. Startup fails closed."""


def resolve_watchlist_symbols(
    *,
    provider_name: str,
    replay_path: Path | None = None,
    explicit: tuple[str, ...] = (),
    watchlist_path: Path | None = None,
) -> tuple[str, ...]:
    """Resolve the watchlist for the standalone runtime (fail-closed).

    Order: explicit symbols > existing watchlist file > provider defaults.
    The longbridge provider has no default and requires an explicit list.
    """
    if explicit:
        for symbol in explicit:
            if not is_valid_symbol(symbol):
                raise McpConfigError(f"invalid symbol format: {symbol}")
        return explicit
    if watchlist_path is not None and Path(watchlist_path).is_file():
        items = Watchlist(watchlist_path).list()
        if items:
            return tuple(item.symbol for item in items)
    if provider_name == "replay":
        if replay_path is None:
            raise McpConfigError("replay provider requires --replay <fixture path>")
        try:
            first = Path(replay_path).read_text(encoding="utf-8").splitlines()[0]
            quotes = json.loads(first)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise McpConfigError(f"cannot read replay fixture: {exc}") from exc
        seen: dict[str, None] = {}
        for quote in quotes:
            symbol = str(quote["symbol"])
            if not is_valid_symbol(symbol):
                raise McpConfigError(f"fixture contains invalid symbol: {symbol}")
            seen.setdefault(symbol, None)
        return tuple(seen)
    if provider_name == "fake":
        return DEFAULT_FAKE_SYMBOLS
    raise McpConfigError(
        f"provider {provider_name} requires an explicit watchlist (--symbols or --watchlist)"
    )


class StandaloneRuntime:
    """One engine, one tick loop, read-only capabilities. No daemon bridge."""

    def __init__(
        self,
        *,
        provider_name: str = "fake",
        replay_path: Path | None = None,
        symbols: tuple[str, ...] = (),
        live: bool = False,
        clock: Clock | None = None,
        scheduler_policy: SchedulerPolicy | None = None,
    ) -> None:
        if provider_name not in PROVIDER_CHOICES:
            raise McpConfigError(
                f"unknown provider {provider_name}; choose from {', '.join(PROVIDER_CHOICES)}"
            )
        if provider_name == "longbridge" and not live:
            raise McpConfigError("longbridge is a live provider; pass --live to opt in explicitly")
        if live and provider_name != "longbridge":
            raise McpConfigError("--live only applies to the longbridge provider")
        if provider_name == "replay" and replay_path is None:
            raise McpConfigError("replay provider requires --replay <fixture path>")
        self._clock = clock if clock is not None else SystemClock()
        self._provider_name = provider_name
        self._replay_path = replay_path
        self._symbols = symbols
        self._live = live
        self._scheduler_policy = scheduler_policy
        self._engine: MarketEngine | None = None
        self._capabilities: MarketCapabilities | None = None
        self._telemetry: TelemetryRuntime | None = None
        self._intelligence = None
        self._tick_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def capabilities(self) -> MarketCapabilities:
        if self._capabilities is None:
            raise McpConfigError("runtime not started")
        return self._capabilities

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            raise McpConfigError("runtime already started")
        # NoOp telemetry by default: MCP queries must not mix observation
        # records into the daemon/CLI evaluation datasets.
        self._telemetry = TelemetryRuntime(self._clock)
        try:
            provider = create_provider(
                self._provider_name, self._clock, replay_path=self._replay_path
            )
        except (ValueError, ProviderError) as exc:
            raise McpConfigError(f"cannot create provider: {exc}") from exc
        symbols = resolve_watchlist_symbols(
            provider_name=self._provider_name,
            replay_path=self._replay_path,
            explicit=self._symbols,
        )
        watchlist = Watchlist(persist=False)
        for symbol in symbols:
            watchlist.add(symbol)
        self._intelligence = optional_intelligence(
            self._clock, telemetry=self._telemetry, enabled=False
        )
        self._engine = MarketEngine(
            clock=self._clock,
            watchlist=watchlist,
            provider=provider,
            scheduler=AdaptiveScheduler(self._clock, self._scheduler_policy),
            buffers=SymbolBuffers(),
            states=MarketStateStore(),
            health=FeedHealthTracker(self._clock),
            intelligence=self._intelligence,
            telemetry=self._telemetry,
        )
        self._capabilities = MarketCapabilities(self._engine, started=lambda: self._running)
        if self._intelligence is not None:
            await self._intelligence.start()
        self._running = True
        self._tick_task = asyncio.create_task(self._tick_loop(), name="mcp-tick-loop")
        logger.info(
            "MCP standalone runtime started: provider=%s live=%s symbols=%s",
            self._provider_name,
            self._live,
            ",".join(symbols),
        )

    async def stop(self) -> None:
        self._running = False
        if self._tick_task is not None:
            self._tick_task.cancel()
            try:
                await self._tick_task
            except asyncio.CancelledError:
                pass
            self._tick_task = None
        if self._intelligence is not None:
            await self._intelligence.shutdown()
            self._intelligence = None
        if self._telemetry is not None:
            self._telemetry.close()
            self._telemetry = None
        logger.info("MCP standalone runtime stopped")

    async def _tick_loop(self) -> None:
        assert self._engine is not None and self._capabilities is not None
        try:
            while True:
                result = await self._engine.tick()
                self._capabilities.observe_tick(result)
                wait = self._engine.scheduler.next_wait_s(self._engine.watchlist.enabled_symbols())
                await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise

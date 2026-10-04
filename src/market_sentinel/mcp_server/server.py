"""FastMCP stdio server exposing Market Sentinel's read-only capabilities.

Thin adapter layer: every tool is a one-to-one mapping onto
``MarketCapabilities``; no market logic lives here. Output shape is a
uniform JSON envelope so error codes stay machine-mappable over any MCP
transport:

    {"ok": true,  "data": <Wire DTO / capability view payload>}
    {"ok": false, "error": {"code": <CapabilityErrorCode>, "message": "..."}}

``isError`` tool results are reserved for transport-level schema violations
(bad argument types) raised by the SDK itself.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from market_sentinel.capabilities import CapabilityError, map_exception
from market_sentinel.mcp_server.runtime import StandaloneRuntime

logger = logging.getLogger(__name__)

SERVER_NAME = "market-sentinel"

RECENT_EVENTS_LIMIT = 200  # mirrors MarketCapabilities.MAX_RECENT_EVENTS


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


async def _guarded(operation: Callable[[], Any]) -> dict[str, Any]:
    """Run one capability read; translate failures into the error envelope.

    The capability call itself is synchronous and runs on the event loop
    (no await inside), so it is atomic with respect to the runtime's tick
    task without any lock.
    """
    try:
        return {"ok": True, "data": operation()}
    except CapabilityError as exc:
        return _error(exc.code.value, str(exc))
    except Exception as exc:  # noqa: BLE001 - defensive boundary, logged to stderr
        mapped = map_exception(exc)
        logger.exception("capability call failed with an unexpected error")
        return _error(mapped.code.value, mapped.code.value)


def build_server(runtime: StandaloneRuntime) -> FastMCP:
    capabilities = runtime.capabilities

    server = FastMCP(
        SERVER_NAME,
        instructions=(
            "Read-only market observation for a small watchlist. Tools query a "
            "deterministic local runtime (fake/replay by default); there are no "
            "write, configuration, execution, or trading tools."
        ),
    )

    @server.tool()
    async def get_market_state() -> dict[str, Any]:
        """Whole-watchlist snapshot: prices, features, levels, feed status, replay progress."""
        return await _guarded(lambda: capabilities.get_market_state().to_wire())

    @server.tool()
    async def get_symbol_state(symbol: str) -> dict[str, Any]:
        """One watched symbol's snapshot (e.g. "600519.SH")."""
        return await _guarded(lambda: capabilities.get_symbol_state(symbol).to_wire())

    @server.tool()
    async def get_active_signals() -> dict[str, Any]:
        """Signals still inside their episode lifecycle, grouped by symbol."""
        return await _guarded(
            lambda: {
                symbol: [signal.to_wire() for signal in signals]
                for symbol, signals in capabilities.get_active_signals().items()
            }
        )

    @server.tool()
    async def get_signal(signal_id: str) -> dict[str, Any]:
        """One active signal by id, including its intelligence annotation when present."""
        return await _guarded(lambda: capabilities.get_signal(signal_id).to_wire())

    @server.tool()
    async def get_feed_health() -> dict[str, Any]:
        """Per-symbol feed health (LIVE/DELAYED/STALE/DISCONNECTED) plus the aggregate."""
        return await _guarded(lambda: capabilities.get_feed_health().to_wire())

    @server.tool()
    async def get_recent_events(
        symbol: str | None = None,
        limit: Annotated[int, Field(ge=1, le=RECENT_EVENTS_LIMIT)] = 20,
    ) -> dict[str, Any]:
        """Recently accepted market events, chronological (newest last); optional symbol filter."""
        events = capabilities.get_recent_events(symbol=symbol, limit=limit)
        return await _guarded(lambda: [event.to_wire() for event in events])

    return server


async def serve(runtime: StandaloneRuntime) -> None:
    """Start the standalone runtime, serve MCP over stdio, then stop cleanly."""
    await runtime.start()
    try:
        server = build_server(runtime)
        await server.run_stdio_async()
    finally:
        await runtime.stop()


def run_stdio(runtime: StandaloneRuntime) -> int:
    """Blocking entrypoint used by `market-sentinel mcp`."""
    asyncio.run(serve(runtime))
    return 0

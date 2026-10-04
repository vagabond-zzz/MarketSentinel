"""Market Sentinel MCP server (optional `[mcp]` extra).

The package import itself never pulls in the MCP SDK; only ``server.py``
does, so the core install and the non-MCP tests run without the extra.
"""

from market_sentinel.mcp_server.runtime import (
    DEFAULT_FAKE_SYMBOLS,
    McpConfigError,
    StandaloneRuntime,
    resolve_watchlist_symbols,
)

__all__ = [
    "DEFAULT_FAKE_SYMBOLS",
    "McpConfigError",
    "StandaloneRuntime",
    "resolve_watchlist_symbols",
]

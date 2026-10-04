"""`market-sentinel mcp` — run the read-only MCP stdio server.

The MCP SDK is an optional dependency (`[mcp]` extra); a missing SDK must
produce an actionable error, never a traceback. Provider and replay come
from the global CLI flags (`--provider`, `--replay`), the watchlist from
the global `--watchlist`.
"""

from __future__ import annotations

import argparse
import sys


def register_mcp(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "mcp", help="run the read-only MCP stdio server (requires the [mcp] extra)"
    )
    parser.add_argument(
        "--symbols",
        default=None,
        help="comma-separated symbols; overrides --watchlist and provider defaults",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="explicit opt-in required by the longbridge live provider",
    )


def _explicit_symbols(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    return tuple(symbol.strip() for symbol in raw.split(",") if symbol.strip())


def run_mcp(args: argparse.Namespace) -> int:
    try:
        from market_sentinel.mcp_server.server import run_stdio
    except ModuleNotFoundError as exc:
        name = exc.name or ""
        if name == "mcp" or name.startswith("mcp."):
            print(
                "MCP support is not installed.\n"
                "Install the optional extra first, then retry:\n"
                "  uv sync --extra mcp                    # project checkout\n"
                "  pip install 'market-sentinel[mcp]'     # installed package",
                file=sys.stderr,
            )
            return 2
        raise
    from market_sentinel.mcp_server.runtime import (
        McpConfigError,
        StandaloneRuntime,
        resolve_watchlist_symbols,
    )

    explicit = _explicit_symbols(args.symbols)
    try:
        symbols = resolve_watchlist_symbols(
            provider_name=args.provider,
            replay_path=args.replay,
            explicit=explicit,
            watchlist_path=None if explicit else args.watchlist,
        )
        runtime = StandaloneRuntime(
            provider_name=args.provider,
            replay_path=args.replay,
            symbols=symbols,
            live=args.live,
        )
    except McpConfigError as exc:
        print(f"market-sentinel mcp: {exc}", file=sys.stderr)
        return 2
    try:
        return run_stdio(runtime)
    except McpConfigError as exc:
        print(f"market-sentinel mcp: {exc}", file=sys.stderr)
        return 2

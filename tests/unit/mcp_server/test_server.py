"""Unit tests for the FastMCP server layer (skipped without the [mcp] extra)."""

from __future__ import annotations

import json
from typing import Any

import pytest

mcp = pytest.importorskip("mcp")

from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402

from market_sentinel.capabilities import CapabilityError  # noqa: E402
from market_sentinel.mcp_server.runtime import StandaloneRuntime  # noqa: E402
from market_sentinel.mcp_server.server import build_server  # noqa: E402

EXPECTED_TOOLS = {
    "get_market_state",
    "get_symbol_state",
    "get_active_signals",
    "get_signal",
    "get_feed_health",
    "get_recent_events",
}

FORBIDDEN_TOOL_MARKERS = (
    "set_",
    "write_",
    "config",
    "tune",
    "deploy",
    "trade",
    "execute",
    "restart",
    "shell",
    "eval",
    "file",
    "fs_",
)


async def _running_server() -> tuple[StandaloneRuntime, Any]:
    runtime = StandaloneRuntime(provider_name="fake")
    await runtime.start()
    return runtime, build_server(runtime)


def _payload(result: Any) -> dict[str, Any]:
    content, structured = result
    if isinstance(structured, dict):
        return structured
    return json.loads(content[0].text)


async def test_exactly_six_read_only_tools() -> None:
    runtime, server = await _running_server()
    try:
        tools = await server.list_tools()
        assert {tool.name for tool in tools} == EXPECTED_TOOLS
        for tool in tools:
            lowered = tool.name.lower()
            assert not any(marker in lowered for marker in FORBIDDEN_TOOL_MARKERS)
    finally:
        await runtime.stop()


async def test_tool_input_schemas() -> None:
    runtime, server = await _running_server()
    try:
        schemas = {tool.name: tool.inputSchema for tool in await server.list_tools()}
        symbol_schema = schemas["get_symbol_state"]
        assert symbol_schema["required"] == ["symbol"]
        assert symbol_schema["properties"]["symbol"]["type"] == "string"
        assert schemas["get_signal"]["required"] == ["signal_id"]
        limit = schemas["get_recent_events"]["properties"]["limit"]
        assert limit["minimum"] == 1 and limit["maximum"] == 200
        assert "symbol" in schemas["get_recent_events"]["properties"]
        assert schemas["get_feed_health"]["properties"] == {}
    finally:
        await runtime.stop()


async def test_get_market_state_envelope() -> None:
    runtime, server = await _running_server()
    try:
        payload = _payload(await server.call_tool("get_market_state", {}))
        assert payload["ok"] is True
        assert payload["data"]["watchlist_count"] == 3
        assert len(payload["data"]["symbols"]) == 3
    finally:
        await runtime.stop()


async def test_get_symbol_state_envelopes() -> None:
    runtime, server = await _running_server()
    try:
        missing = _payload(await server.call_tool("get_symbol_state", {"symbol": "00700.HK"}))
        assert missing["ok"] is False
        assert missing["error"]["code"] == "not_found"

        invalid = _payload(await server.call_tool("get_symbol_state", {"symbol": "BAD"}))
        assert invalid["ok"] is False
        assert invalid["error"]["code"] == "invalid_argument"
    finally:
        await runtime.stop()


async def test_schema_violation_surfaces_as_is_error() -> None:
    runtime, server = await _running_server()
    try:
        with pytest.raises(ToolError):
            await server.call_tool("get_symbol_state", {"symbol": 123})
    finally:
        await runtime.stop()


async def test_get_signal_error_envelopes() -> None:
    runtime, server = await _running_server()
    try:
        missing = _payload(await server.call_tool("get_signal", {"signal_id": "deadbeef" * 4}))
        assert missing["ok"] is False
        assert missing["error"]["code"] == "not_found"

        invalid = _payload(await server.call_tool("get_signal", {"signal_id": "  "}))
        assert invalid["error"]["code"] == "invalid_argument"
    finally:
        await runtime.stop()


async def test_get_active_signals_and_recent_events_envelopes() -> None:
    runtime, server = await _running_server()
    try:
        active = _payload(await server.call_tool("get_active_signals", {}))
        assert active == {"ok": True, "data": {}}
        recent = _payload(await server.call_tool("get_recent_events", {"limit": 3}))
        assert recent == {"ok": True, "data": []}
    finally:
        await runtime.stop()


async def test_not_running_maps_to_envelope() -> None:
    runtime = StandaloneRuntime(provider_name="fake")
    await runtime.start()
    server = build_server(runtime)
    await runtime.stop()
    payload = _payload(await server.call_tool("get_market_state", {}))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_running"


async def test_envelopes_leak_no_secrets_or_traces() -> None:
    runtime, server = await _running_server()
    try:
        calls: list[Any] = []
        calls.append(_payload(await server.call_tool("get_market_state", {})))
        calls.append(_payload(await server.call_tool("get_feed_health", {})))
        calls.append(_payload(await server.call_tool("get_active_signals", {})))
        bad = _payload(await server.call_tool("get_symbol_state", {"symbol": "NOPE.XX"}))
        calls.append(bad)
        blob = json.dumps(calls, ensure_ascii=False).lower()
        forbidden = ("longbridge", "app_secret", "access_token", "dashscope", "sk-", "traceback")
        for marker in forbidden:
            assert marker not in blob, marker
    finally:
        await runtime.stop()


async def test_unexpected_capability_error_maps_to_internal_envelope() -> None:
    """An unexpected Python exception must surface as a structured internal code."""
    from market_sentinel.mcp_server.server import _guarded

    def broken() -> None:
        raise RuntimeError("boom")

    payload = await _guarded(broken)
    assert payload == {
        "ok": False,
        "error": {"code": "internal", "message": "internal"},
    }


async def test_capability_error_subclass_boundary() -> None:
    """Sanity: CapabilityError from the facade flows into the envelope path."""
    runtime, server = await _running_server()
    try:
        with pytest.raises(CapabilityError):
            runtime.capabilities.get_symbol_state("BAD")
    finally:
        await runtime.stop()

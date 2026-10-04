"""Integration test: real `market-sentinel mcp` process over stdio.

Verifies stdout carries only MCP protocol traffic, all six tools respond,
errors keep their stable codes, and stdin close shuts the process down
cleanly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.integration
def test_mcp_stdio_round_trip(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")

    env = os.environ.copy()
    env["MARKET_SENTINEL_DATA_DIR"] = str(tmp_path)
    proc = subprocess.Popen(
        [uv, "run", "--directory", str(REPO), "market-sentinel", "--provider", "fake", "mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(REPO),
        env=env,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    stdout_lines: list[str] = []
    try:

        def send(payload: dict) -> None:
            assert proc.stdin is not None
            proc.stdin.write(json.dumps(payload) + "\n")
            proc.stdin.flush()

        def recv() -> dict:
            assert proc.stdout is not None
            line = proc.stdout.readline()
            stdout_lines.append(line)
            return json.loads(line)

        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "0"},
                },
            }
        )
        init = recv()
        assert init["result"]["serverInfo"]["name"] == "market-sentinel"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in recv()["result"]["tools"]}
        assert names == {
            "get_market_state",
            "get_symbol_state",
            "get_active_signals",
            "get_signal",
            "get_feed_health",
            "get_recent_events",
        }

        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_feed_health", "arguments": {}},
            }
        )
        health = recv()
        assert health["result"].get("isError") is not True
        payload = json.loads(health["result"]["content"][0]["text"])
        assert payload["ok"] is True
        assert payload["data"]["symbols"]

        send(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "get_symbol_state",
                    "arguments": {"symbol": "NOPE.XX"},
                },
            }
        )
        invalid = recv()
        assert invalid["result"].get("isError") is not True
        error = json.loads(invalid["result"]["content"][0]["text"])
        assert error["ok"] is False
        assert error["error"]["code"] == "invalid_argument"

        # stdin close = clean shutdown; runtime tick task must not linger.
        proc.stdin.close()
        code = proc.wait(timeout=30)
        assert code == 0
        leftover = proc.stdout.read()
        assert leftover == "", f"stdout carried non-protocol bytes: {leftover!r}"
    finally:
        if proc.poll() is None:
            proc.kill()
        stderr = proc.stderr.read()
        proc.stderr.close()

    # Every stdout line must be a valid JSON-RPC message (no banners/logs).
    for line in stdout_lines:
        message = json.loads(line)
        assert message["jsonrpc"] == "2.0"
    # Diagnostics belong on stderr.
    assert "MCP standalone runtime started" in stderr

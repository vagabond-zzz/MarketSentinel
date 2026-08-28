from __future__ import annotations

import asyncio
import io
import json
import queue
import time
from typing import Any

import pytest
from tests.unit.ipc.helpers import command, make_engine, parse_stdout

from market_sentinel.ipc.daemon import MarketDaemon
from market_sentinel.ipc.protocol import DaemonPhase


class BlockingStdin:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()

    def readline(self) -> str:
        return self._queue.get()

    def push(self, line: str) -> None:
        self._queue.put(line if line.endswith("\n") or line == "" else line + "\n")

    def close(self) -> None:
        self._queue.put("")


async def _drain(stdout: io.StringIO, count: int, timeout: float = 5.0) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        messages = parse_stdout(stdout.getvalue())
        if len(messages) >= count:
            return messages
        await asyncio.sleep(0.01)
    raise TimeoutError(stdout.getvalue())


async def _run_script(lines: list[str]) -> list[dict[str, Any]]:
    _, _, engine = make_engine()
    stdin = io.StringIO("".join(lines))
    stdout = io.StringIO()
    daemon = MarketDaemon(engine, stdin=stdin, stdout=stdout)
    await asyncio.wait_for(daemon.run(), timeout=5)
    return parse_stdout(stdout.getvalue())


@pytest.mark.asyncio
async def test_start_before_hello_is_not_ready() -> None:
    messages = await _run_script([command("start", "s1"), command("shutdown", "x")])
    assert messages[0]["type"] == "error"
    assert messages[0]["code"] == "not_ready"
    assert messages[-1]["type"] == "shutdown_ack"


@pytest.mark.asyncio
async def test_hello_start_pause_resume_get_state_shutdown() -> None:
    messages = await _run_script(
        [
            command("hello", "h1", host="test"),
            command("set_watchlist", "w1", items=[{"symbol": "00700.HK", "enabled": True}]),
            command("get_state", "g1"),
            command("start", "s1"),
            command("start", "s2"),
            command("pause", "p1"),
            command("pause", "p2"),
            command("resume", "r1"),
            command("resume", "r2"),
            command("pause", "p3"),
            command("get_state", "g2"),
            command("shutdown", "x1"),
        ]
    )
    types = [item["type"] for item in messages]
    assert types[0] == "ready"
    assert messages[0]["core_version"] == "0.5.0"
    assert messages[1]["type"] == "ack"
    assert messages[1]["watchlist_count"] == 1
    assert messages[2]["type"] == "state"
    assert messages[2]["request_id"] == "g1"
    assert messages[2]["state"]["symbols"][0]["symbol"] == "00700.HK"
    assert any(item.get("request_id") == "s1" and item["type"] == "ack" for item in messages)
    assert any(item.get("request_id") == "s2" and item["type"] == "ack" for item in messages)
    assert any(item.get("request_id") == "p1" and item["type"] == "ack" for item in messages)
    assert any(item.get("request_id") == "p2" and item["type"] == "ack" for item in messages)
    assert any(item.get("request_id") == "r1" and item["type"] == "ack" for item in messages)
    assert any(item.get("request_id") == "r2" and item["type"] == "ack" for item in messages)
    assert any(item.get("request_id") == "g2" and item["type"] == "state" for item in messages)
    assert messages[-1]["type"] == "shutdown_ack"
    assert messages[-1]["request_id"] == "x1"


@pytest.mark.asyncio
async def test_start_while_paused_errors() -> None:
    messages = await _run_script(
        [
            command("hello", "h1"),
            command("start", "s1"),
            command("pause", "p1"),
            command("start", "s2"),
            command("shutdown", "x"),
        ]
    )
    start_paused = next(item for item in messages if item.get("request_id") == "s2")
    assert start_paused["type"] == "error"
    assert start_paused["code"] == "paused"


@pytest.mark.asyncio
async def test_pause_before_start_is_not_started() -> None:
    messages = await _run_script(
        [
            command("hello", "h1"),
            command("pause", "p1"),
            command("resume", "r1"),
            command("shutdown", "x"),
        ]
    )
    assert (
        next(item for item in messages if item.get("request_id") == "p1")["code"] == "not_started"
    )
    assert (
        next(item for item in messages if item.get("request_id") == "r1")["code"] == "not_started"
    )


@pytest.mark.asyncio
async def test_get_state_allowed_in_ready() -> None:
    messages = await _run_script(
        [command("hello", "h1"), command("get_state", "g1"), command("shutdown", "x")]
    )
    state = next(item for item in messages if item.get("request_id") == "g1")
    assert state["type"] == "state"
    assert state["state"]["watchlist_count"] == 0


@pytest.mark.asyncio
async def test_invalid_json_unknown_type_mismatch() -> None:
    messages = await _run_script(
        [
            "{bad\n",
            command("hello", "h1"),
            '{"protocol_version":2,"type":"hello","request_id":"h2"}\n',
            '{"protocol_version":1,"type":"nope","request_id":"n1"}\n',
            command("shutdown", "x"),
        ]
    )
    codes = [item.get("code") for item in messages if item["type"] == "error"]
    assert "invalid_json" in codes
    assert "protocol_mismatch" in codes
    assert "unknown_type" in codes


@pytest.mark.asyncio
async def test_duplicate_hello_is_idempotent_ready() -> None:
    messages = await _run_script(
        [
            command("hello", "h1"),
            command("hello", "h2"),
            command("shutdown", "x"),
        ]
    )
    readies = [item for item in messages if item["type"] == "ready"]
    assert [item["request_id"] for item in readies] == ["h1", "h2"]


@pytest.mark.asyncio
async def test_set_watchlist_does_not_persist(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "data" / "watchlist.json"
    path.parent.mkdir()
    path.write_text('{"items":[{"symbol":"KEEP.HK","enabled":true}]}', encoding="utf-8")
    messages = await _run_script(
        [
            command("hello", "h1"),
            command("set_watchlist", "w1", items=[{"symbol": "00700.HK", "enabled": True}]),
            command("shutdown", "x"),
        ]
    )
    assert any(item.get("request_id") == "w1" and item["type"] == "ack" for item in messages)
    assert json.loads(path.read_text(encoding="utf-8"))["items"][0]["symbol"] == "KEEP.HK"


@pytest.mark.asyncio
async def test_windows_safe_stdin_does_not_block_event_loop() -> None:
    _, _, engine = make_engine()
    stdin = BlockingStdin()
    stdout = io.StringIO()
    daemon = MarketDaemon(engine, stdin=stdin, stdout=stdout)
    task = asyncio.create_task(daemon.run())
    progressed = False

    async def ping() -> None:
        nonlocal progressed
        await asyncio.sleep(0.05)
        progressed = True

    await ping()
    assert progressed is True
    assert daemon.phase is DaemonPhase.AWAITING_HELLO
    stdin.push(command("hello", "h1"))
    await _drain(stdout, 1)
    stdin.push(command("shutdown", "x"))
    await asyncio.wait_for(task, timeout=5)
    messages = parse_stdout(stdout.getvalue())
    assert messages[0]["type"] == "ready"
    assert messages[-1]["type"] == "shutdown_ack"


@pytest.mark.asyncio
async def test_start_emits_unsolicited_state() -> None:
    _, _, engine = make_engine()
    stdin = BlockingStdin()
    stdout = io.StringIO()
    daemon = MarketDaemon(engine, stdin=stdin, stdout=stdout)
    task = asyncio.create_task(daemon.run())
    stdin.push(command("hello", "h1"))
    await _drain(stdout, 1)
    stdin.push(command("set_watchlist", "w1", items=[{"symbol": "00700.HK", "enabled": True}]))
    await _drain(stdout, 2)
    stdin.push(command("start", "s1"))
    deadline_messages = await _drain(stdout, 4)
    assert any(item["type"] == "state" and "request_id" not in item for item in deadline_messages)
    stdin.push(command("shutdown", "x"))
    await asyncio.wait_for(task, timeout=5)

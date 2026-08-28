from __future__ import annotations

import asyncio
import io

import pytest
from tests.unit.ipc.helpers import command, make_engine, parse_stdout

from market_sentinel.ipc.daemon import MarketDaemon
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.contract import TelemetryName
from market_sentinel.telemetry.host_interaction import parse_host_interaction
from market_sentinel.telemetry.runtime import TelemetryRuntime


@pytest.mark.asyncio
async def test_host_presented_and_badge_reset() -> None:
    memory = InMemoryTelemetryCollector()
    clock, _, engine = make_engine()
    engine.telemetry.close()
    runtime = TelemetryRuntime(clock, memory, run_id=engine.telemetry.run_id)
    engine.telemetry = runtime
    stdin = io.StringIO(
        "".join(
            [
                command("hello", "h1"),
                command(
                    "host_interaction",
                    "p1",
                    action="alert_presented",
                    signal_id="sig-1",
                    created_timestamp=1.5,
                ),
                command(
                    "host_interaction",
                    "p2",
                    action="alert_presented",
                    signal_id="sig-2",
                    created_timestamp=1.6,
                ),
                command(
                    "host_interaction",
                    "r1",
                    action="alert_badge_reset",
                    created_timestamp=2.0,
                ),
                command("shutdown", "x"),
            ]
        )
    )
    stdout = io.StringIO()
    await asyncio.wait_for(MarketDaemon(engine, stdin=stdin, stdout=stdout).run(), timeout=5)
    messages = parse_stdout(stdout.getvalue())
    assert [item["type"] for item in messages if item.get("request_id") in {"p1", "p2", "r1"}] == [
        "ack",
        "ack",
        "ack",
    ]
    names = [item.name for item in memory.events]
    assert names.count(TelemetryName.ALERT_PRESENTED) == 2
    assert names.count(TelemetryName.ALERT_BADGE_RESET) == 1
    assert TelemetryName.ALERT_DISMISSED not in names
    assert {item.run_id for item in memory.events} == {runtime.run_id}


@pytest.mark.asyncio
async def test_host_interaction_rejects_workspace_payload() -> None:
    _, _, engine = make_engine()
    stdin = io.StringIO(
        "".join(
            [
                command("hello", "h1"),
                command(
                    "host_interaction",
                    "bad",
                    action="alert_presented",
                    signal_id="sig-1",
                    workspace="/secret",
                ),
                command("shutdown", "x"),
            ]
        )
    )
    stdout = io.StringIO()
    await asyncio.wait_for(MarketDaemon(engine, stdin=stdin, stdout=stdout).run(), timeout=5)
    messages = parse_stdout(stdout.getvalue())
    error = next(item for item in messages if item.get("request_id") == "bad")
    assert error["type"] == "error"
    assert error["code"] == "invalid_payload"


def test_parse_host_interaction_requires_signal_id_for_presented() -> None:
    error = parse_host_interaction(
        {
            "protocol_version": 1,
            "type": "host_interaction",
            "request_id": "r",
            "action": "alert_presented",
        }
    )
    assert isinstance(error, str)
    reset = parse_host_interaction(
        {
            "protocol_version": 1,
            "type": "host_interaction",
            "request_id": "r",
            "action": "alert_badge_reset",
        }
    )
    assert not isinstance(reset, str)
    assert reset.signal_id is None

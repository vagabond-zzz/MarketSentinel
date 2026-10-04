"""Unit tests for the MCP standalone runtime (no MCP SDK required)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from market_sentinel.capabilities import CapabilityError, CapabilityErrorCode
from market_sentinel.mcp_server import (
    DEFAULT_FAKE_SYMBOLS,
    McpConfigError,
    StandaloneRuntime,
    resolve_watchlist_symbols,
)
from market_sentinel.scheduler.policy import SchedulerPolicy

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"
FAST_POLICY = SchedulerPolicy(
    cold_interval_s=0.01,
    warm_interval_s=0.01,
    hot_interval_s=0.01,
    hot_downgrade_dwell_s=0.0,
    warm_downgrade_dwell_s=0.0,
)


def test_resolve_defaults_to_fake_symbols() -> None:
    assert resolve_watchlist_symbols(provider_name="fake") == DEFAULT_FAKE_SYMBOLS


def test_resolve_explicit_symbols_validate_format() -> None:
    assert resolve_watchlist_symbols(provider_name="fake", explicit=("600519.SH",)) == (
        "600519.SH",
    )
    with pytest.raises(McpConfigError):
        resolve_watchlist_symbols(provider_name="fake", explicit=("not-a-symbol",))


def test_resolve_replay_derives_symbols_from_fixture() -> None:
    symbols = resolve_watchlist_symbols(
        provider_name="replay", replay_path=FIXTURE_DIR / "multi_a_share_ui.jsonl"
    )
    assert symbols == ("600519.SH", "000001.SZ", "300750.SZ")


def test_resolve_replay_requires_fixture() -> None:
    with pytest.raises(McpConfigError):
        resolve_watchlist_symbols(provider_name="replay", replay_path=None)


def test_resolve_longbridge_fails_closed_without_explicit_symbols() -> None:
    with pytest.raises(McpConfigError):
        resolve_watchlist_symbols(provider_name="longbridge")


def test_longbridge_requires_explicit_live_opt_in() -> None:
    with pytest.raises(McpConfigError):
        StandaloneRuntime(provider_name="longbridge")


def test_live_flag_only_applies_to_longbridge() -> None:
    with pytest.raises(McpConfigError):
        StandaloneRuntime(provider_name="fake", live=True)


def test_unknown_provider_rejected() -> None:
    with pytest.raises(McpConfigError):
        StandaloneRuntime(provider_name="http")


async def test_capabilities_unavailable_before_start() -> None:
    runtime = StandaloneRuntime(provider_name="fake")
    with pytest.raises(McpConfigError):
        _ = runtime.capabilities


async def test_start_stop_cycle() -> None:
    runtime = StandaloneRuntime(provider_name="fake")
    await runtime.start()
    assert runtime.running
    state = runtime.capabilities.get_market_state()
    assert state.watchlist_count == len(DEFAULT_FAKE_SYMBOLS)
    health = runtime.capabilities.get_feed_health()
    assert health.symbols
    await runtime.stop()
    assert not runtime.running
    with pytest.raises(CapabilityError) as excinfo:
        runtime.capabilities.get_market_state()
    assert excinfo.value.code is CapabilityErrorCode.NOT_RUNNING
    pending = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and not task.done()
    ]
    assert pending == [], "tick loop must not survive stop()"


async def test_stop_is_idempotent() -> None:
    runtime = StandaloneRuntime(provider_name="fake")
    await runtime.stop()
    await runtime.stop()


async def test_double_start_rejected() -> None:
    runtime = StandaloneRuntime(provider_name="fake")
    await runtime.start()
    try:
        with pytest.raises(McpConfigError):
            await runtime.start()
    finally:
        await runtime.stop()


async def test_replay_runtime_feeds_recent_events() -> None:
    runtime = StandaloneRuntime(
        provider_name="replay",
        replay_path=FIXTURE_DIR / "rapid_move.jsonl",
        scheduler_policy=FAST_POLICY,
    )
    await runtime.start()
    try:
        await asyncio.sleep(0.3)
        events = runtime.capabilities.get_recent_events()
        assert events, "tick loop must feed observe_tick so recent events are queryable"
        for event in events:
            wire = event.to_wire()
            assert "metrics" not in wire
            assert "dedupe_key" not in wire
            assert "ttl_s" not in wire
        limited = runtime.capabilities.get_recent_events(limit=1)
        assert len(limited) == 1
    finally:
        await runtime.stop()


async def test_replay_derives_watchlist_without_explicit_symbols() -> None:
    runtime = StandaloneRuntime(
        provider_name="replay", replay_path=FIXTURE_DIR / "rapid_move.jsonl"
    )
    await runtime.start()
    try:
        state = runtime.capabilities.get_market_state()
        assert state.watchlist_count >= 1
    finally:
        await runtime.stop()

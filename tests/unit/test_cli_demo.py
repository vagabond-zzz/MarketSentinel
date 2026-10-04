"""Tests for `market-sentinel demo`: deterministic, offline, no secrets."""

from __future__ import annotations

import re

from market_sentinel.cli.main import main

UUID_HEX = re.compile(r"\b[0-9a-f]{32}\b")


def test_demo_runs_and_is_deterministic(capsys) -> None:
    assert main(["demo"]) == 0
    first = capsys.readouterr().out
    assert main(["demo"]) == 0
    second = capsys.readouterr().out

    assert "deterministic replay walkthrough" in first
    assert "provider: replay (multi_a_share_ui.jsonl)" in first
    assert "no API key" in first
    assert "[pipeline]" in first
    assert "replay batches ticked : 43" in first
    assert "capability get_market_state()" in first
    assert "capability get_feed_health()" in first
    assert "capability get_active_signals()" in first
    assert "capability get_recent_events(limit=3)" in first
    assert 'capability get_signal("' in first
    assert "demo complete — no API keys, no network, no files written." in first

    # Signal/event IDs are runtime UUIDs; everything else must be identical.
    assert UUID_HEX.sub("<uuid>", first) == UUID_HEX.sub("<uuid>", second)


def test_demo_does_not_write_telemetry(tmp_path) -> None:
    assert main(["demo"]) == 0
    assert not (tmp_path / "ms-data").exists()


def test_demo_missing_fixture_fails_closed(tmp_path) -> None:
    missing = tmp_path / "nope.jsonl"
    assert main(["demo", "--fixture", str(missing)]) == 2

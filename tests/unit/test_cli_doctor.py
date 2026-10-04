"""Tests for `market-sentinel doctor`: read-only diagnostics, no mutation."""

from __future__ import annotations

import json

from market_sentinel.cli.main import main


def test_doctor_reports_and_exits_zero(capsys) -> None:
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "✓ Python" in out
    assert "✓ package" in out
    assert "market-sentinel 0.6.5 (protocol 1)" in out
    assert "provider fake" in out
    assert "ZCode integration: not implemented (planned milestone M4)" in out
    assert "DeepSeek Harness integration: not implemented (planned milestone M5)" in out


def test_doctor_json_output_is_parseable(capsys) -> None:
    assert main(["doctor", "--json"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["ok"] is True
    labels = {item["check"] for item in record["checks"]}
    assert {"Python", "package", "intelligence", "telemetry directory"} <= labels


def test_doctor_does_not_print_secret_values(capsys, monkeypatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-secret-value-for-test")
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "DASHSCOPE_API_KEY is set" in out
    assert "sk-secret-value-for-test" not in out
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "DASHSCOPE_API_KEY not set" in out


def test_doctor_creates_nothing(tmp_path) -> None:
    data_dir = tmp_path / "ms-data"
    assert main(["doctor"]) == 0
    assert not data_dir.exists(), "doctor must not create or write the data directory"

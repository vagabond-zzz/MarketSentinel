"""Tests for `market-sentinel doctor`: read-only diagnostics, no mutation."""

from __future__ import annotations

import json

from market_sentinel.cli import doctor as doctor_module
from market_sentinel.cli.main import main


def test_doctor_reports_and_exits_zero(capsys) -> None:
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "✓ Python" in out
    assert "✓ package" in out
    assert "market-sentinel 0.6.5 (protocol 1)" in out
    assert "provider fake" in out
    assert "ZCode integration" in out
    assert "DeepSeek Harness integration: not implemented (planned milestone M5)" in out


def test_doctor_detects_zcode_registration(capsys, monkeypatch, tmp_path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"mcp": {"servers": {"market-sentinel": {"type": "stdio", "command": "uv"}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor_module, "_zcode_config_paths", lambda: [("user config", config)])
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "ZCode integration: market-sentinel server registered (user config)" in out
    assert "not registered" not in out


def test_doctor_reports_unregistered_zcode(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        doctor_module, "_zcode_config_paths", lambda: [("user config", tmp_path / "absent.json")]
    )
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "ZCode integration: not registered" in out


def test_doctor_registration_does_not_print_config_values(capsys, monkeypatch, tmp_path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "mcp": {
                    "servers": {
                        "market-sentinel": {
                            "command": "D:/secret/path/uv.exe",
                            "token": "supersecret",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor_module, "_zcode_config_paths", lambda: [("user config", config)])
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "supersecret" not in out
    assert "D:/secret/path" not in out


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

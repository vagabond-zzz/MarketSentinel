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


# ---------------------------------------------------------------------------
# F1 regression: telemetry-directory check must walk the whole ancestor chain
# instead of failing when the direct parent is missing (M9 finding F1).


def test_telemetry_check_existing_writable_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(doctor_module, "resolve_data_dir", lambda override: tmp_path)
    status, _label, detail = doctor_module._check_telemetry_dir()[0]
    assert status == "✓" and "writable" in detail


def test_telemetry_check_missing_direct_parent(monkeypatch, tmp_path) -> None:
    target = tmp_path / "ms-data"
    monkeypatch.setattr(doctor_module, "resolve_data_dir", lambda override: target)
    status, _label, detail = doctor_module._check_telemetry_dir()[0]
    assert status == "✓" and "creatable on first run" in detail
    assert not target.exists(), "doctor must not create the directory"


def test_telemetry_check_multiple_missing_ancestors(monkeypatch, tmp_path) -> None:
    target = tmp_path / "level1" / "level2" / "level3"
    monkeypatch.setattr(doctor_module, "resolve_data_dir", lambda override: target)
    status, _label, detail = doctor_module._check_telemetry_dir()[0]
    assert status == "✓" and "creatable on first run" in detail
    assert not (tmp_path / "level1").exists(), "doctor must not create any ancestor"


def test_telemetry_check_unwritable_ancestor_fails(monkeypatch, tmp_path) -> None:
    target = tmp_path / "a" / "b"
    monkeypatch.setattr(doctor_module, "resolve_data_dir", lambda override: target)
    monkeypatch.setattr(doctor_module.os, "access", lambda path, mode: False)
    status, _label, detail = doctor_module._check_telemetry_dir()[0]
    assert status == "✗" and "no writable ancestor" in detail


def test_first_existing_ancestor_walk(monkeypatch, tmp_path) -> None:
    deep = tmp_path / "x" / "y" / "z"
    assert doctor_module._first_existing_ancestor(deep) == tmp_path
    assert doctor_module._first_existing_ancestor(tmp_path) == tmp_path


def test_telemetry_check_missing_ancestor_chain_linux_style(monkeypatch, tmp_path) -> None:
    """F1 original report: ~/.local/share missing entirely (Linux runner shape)."""
    home = tmp_path / "home"
    target = home / ".local" / "share" / "market-sentinel"
    monkeypatch.setattr(doctor_module, "resolve_data_dir", lambda override: target)
    status, _label, detail = doctor_module._check_telemetry_dir()[0]
    assert status == "✓" and "creatable on first run" in detail


# ---------------------------------------------------------------------------
# F4 regression: installed-package doctor must not point at a bogus
# <site-packages>/tests/fixtures path when the repository is absent.


def test_doctor_replay_line_in_checkout(monkeypatch, tmp_path, capsys) -> None:
    fixtures = tmp_path / "tests" / "fixtures"
    fixtures.mkdir(parents=True)
    monkeypatch.setattr(doctor_module, "default_fixture_dir", lambda: fixtures)
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "✓ provider replay: fixture corpus found: fixtures/" in out


def test_doctor_replay_line_installed_package(monkeypatch, tmp_path, capsys) -> None:
    absent = tmp_path / "lib" / "tests" / "fixtures"
    monkeypatch.setattr(doctor_module, "default_fixture_dir", lambda: absent)
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "corpus ships with the repository checkout" in out
    assert "fixture directory not found" not in out
    assert str(absent) not in out

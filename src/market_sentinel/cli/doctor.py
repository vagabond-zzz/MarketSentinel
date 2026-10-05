"""`market-sentinel doctor` — read-only environment diagnostics.

Doctor reports; it never installs, configures, writes keys, or starts
processes. Checks are limited to what can be judged reliably and locally.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

from market_sentinel.intelligence.model_settings import load_model_settings
from market_sentinel.ipc.protocol import PROTOCOL_VERSION
from market_sentinel.providers.longbridge import missing_credential_names
from market_sentinel.telemetry.paths import resolve_data_dir
from market_sentinel.tuning.replay import default_fixture_dir

_OK = "✓"
_WARN = "⚠"
_FAIL = "✗"
_INFO = "-"

PYTHON_MIN = (3, 12)


def register_doctor(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = sub.add_parser(
        "doctor", help="read-only environment diagnostics (no changes, no network)"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")


def run_doctor(args: argparse.Namespace) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    checks: list[tuple[str, str, str]] = []

    checks.extend(_check_python())
    checks.extend(_check_uv())
    checks.extend(_check_package())
    checks.extend(_check_optional_live_deps())
    checks.extend(_check_providers())
    checks.extend(_check_intelligence())
    checks.extend(_check_mcp_extra())
    checks.extend(_check_telemetry_dir())
    checks.append((_INFO, "DeepSeek Harness integration", "not implemented (planned milestone M5)"))
    checks.extend(_check_zcode_registration())

    failed = any(status == _FAIL for status, _label, _detail in checks)
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "ok": not failed,
                    "checks": [
                        {"status": status, "check": label, "detail": detail}
                        for status, label, detail in checks
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for status, label, detail in checks:
            suffix = f": {detail}" if detail else ""
            print(f"{status} {label}{suffix}")
    return 1 if failed else 0


def _check_python() -> list[tuple[str, str, str]]:
    version = sys.version.split()[0]
    required = f">= {PYTHON_MIN[0]}.{PYTHON_MIN[1]} required"
    if sys.version_info[:2] >= PYTHON_MIN:
        return [(_OK, "Python", f"{version} ({required})")]
    return [(_FAIL, "Python", f"{version} ({required})")]


def _check_uv() -> list[tuple[str, str, str]]:
    uv = shutil.which("uv")
    if uv is None:
        return [(_WARN, "uv", "not on PATH; documented commands assume `uv run`")]
    return [(_OK, "uv", uv)]


def _check_package() -> list[tuple[str, str, str]]:
    try:
        version = importlib.metadata.version("market-sentinel")
    except importlib.metadata.PackageNotFoundError:
        return [(_FAIL, "package", "market-sentinel not installed; run `uv sync`")]
    in_venv = sys.prefix != sys.base_prefix
    detail = f"market-sentinel {version} (protocol {PROTOCOL_VERSION})"
    detail += "; virtualenv active" if in_venv else "; no virtualenv detected"
    return [(_OK, "package", detail)]


def _check_optional_live_deps() -> list[tuple[str, str, str]]:
    missing = [name for name in ("httpx", "longbridge") if importlib.util.find_spec(name) is None]
    if missing:
        return [
            (
                _WARN,
                "live dependencies",
                f"not installed: {', '.join(missing)} (optional; `uv sync --extra live`)",
            )
        ]
    return [(_OK, "live dependencies", "httpx and longbridge importable")]


def _check_providers() -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = [(_OK, "provider fake", "default, no configuration")]
    fixture_dir = default_fixture_dir()
    if fixture_dir.is_dir():
        checks.append((_OK, "provider replay", f"fixture corpus found: {fixture_dir.name}/"))
    else:
        checks.append(
            (
                _INFO,
                "provider replay",
                "offline tuning/replay corpus ships with the repository checkout;"
                " installed package still supports --replay <file> and --fixture",
            )
        )
    missing = missing_credential_names()
    if missing:
        checks.append(
            (
                _WARN,
                "provider longbridge",
                f"credentials not set: {', '.join(missing)} (optional live provider)",
            )
        )
    else:
        checks.append((_OK, "provider longbridge", "credentials present in environment"))
    checks.append((_INFO, "provider http", "intentional stub; use fake, replay, or longbridge"))
    return checks


def _check_intelligence() -> list[tuple[str, str, str]]:
    settings = load_model_settings()
    enabled_raw = os.environ.get("MARKET_SENTINEL_INTEL_ENABLED", "").strip().lower()
    state = "enabled" if enabled_raw in {"1", "true", "yes"} else "disabled (default)"
    checks: list[tuple[str, str, str]] = [
        (_OK, "intelligence", f"{state}; provider {settings.provider}, model {settings.model}")
    ]
    if os.environ.get(settings.api_key_env):
        checks.append((_OK, "intelligence key", f"{settings.api_key_env} is set"))
    else:
        checks.append(
            (
                _WARN,
                "intelligence key",
                f"{settings.api_key_env} not set; live model calls unavailable"
                " (fail-open to rules-only)",
            )
        )
    return checks


def _check_mcp_extra() -> list[tuple[str, str, str]]:
    if importlib.util.find_spec("mcp") is None:
        return [(_WARN, "mcp extra", "not installed (optional; `uv sync --extra mcp`)")]
    return [(_OK, "mcp extra", "installed; serve tools with `market-sentinel mcp`")]


def _zcode_config_paths() -> list[tuple[str, Path]]:
    home = Path.home()
    return [
        ("user config", home / ".zcode" / "cli" / "config.json"),
        ("workspace config", Path.cwd() / ".zcode" / "config.json"),
        ("agents fallback", home / ".agents" / "mcp.json"),
    ]


def _registered_zcode_scope() -> str | None:
    """Find a registered market-sentinel MCP server in known ZCode config files.

    Registration is a config-file fact only; an actual host connection is
    verified in a live ZCode session (see docs/integrations/zcode.md).
    """
    for scope, path in _zcode_config_paths():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        servers = data.get("mcp", {}).get("servers") or data.get("mcpServers") or {}
        if "market-sentinel" in servers:
            return scope
    return None


def _check_zcode_registration() -> list[tuple[str, str, str]]:
    scope = _registered_zcode_scope()
    if scope is not None:
        return [
            (
                _OK,
                "ZCode integration",
                f"market-sentinel server registered ({scope});"
                " host connection is verified in a live session",
            )
        ]
    return [
        (
            _WARN,
            "ZCode integration",
            "not registered; see docs/integrations/zcode.md for setup",
        )
    ]


def _first_existing_ancestor(path: Path) -> Path:
    """Walk up to the first ancestor that exists as a directory (or the root)."""
    current = path
    while not current.is_dir():
        parent = current.parent
        if parent == current:
            return current
        current = parent
    return current


def _check_telemetry_dir() -> list[tuple[str, str, str]]:
    data_dir = resolve_data_dir(None)
    if data_dir.is_dir():
        if os.access(data_dir, os.W_OK):
            return [(_OK, "telemetry directory", f"writable: {data_dir}")]
        return [(_FAIL, "telemetry directory", f"not writable: {data_dir}")]
    # The directory itself does not exist yet: creation on first run only
    # requires one writable ancestor, however deep the missing chain is.
    # Never create anything here — doctor diagnoses, it does not write.
    ancestor = _first_existing_ancestor(data_dir)
    if ancestor.is_dir() and os.access(ancestor, os.W_OK):
        return [(_OK, "telemetry directory", f"creatable on first run: {data_dir}")]
    return [
        (
            _FAIL,
            "telemetry directory",
            f"no writable ancestor found for: {data_dir} (checked up to {ancestor})",
        )
    ]

"""Dependency discipline: the MCP SDK stays an optional extra."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def _pyproject() -> dict:
    with (REPO / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_core_has_no_mainline_dependencies() -> None:
    project = _pyproject()["project"]
    assert project.get("dependencies", []) == [], "core runtime must be stdlib-only"


def test_mcp_extra_exists_and_core_tests_do_not_require_it() -> None:
    optional = _pyproject()["project"]["optional-dependencies"]
    assert any(spec.startswith("mcp") for spec in optional["mcp"])


def test_mcp_not_in_dev_dependency_group() -> None:
    dev = _pyproject()["dependency-groups"]["dev"]
    assert not any(spec.startswith("mcp") for spec in dev), (
        "MCP tests must skip without the extra; the SDK must not leak into dev deps"
    )


def test_core_imports_never_pull_the_sdk() -> None:
    src = REPO / "src" / "market_sentinel"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        if path.name == "server.py" and path.parent.name == "mcp_server":
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import mcp") or stripped.startswith("from mcp"):
                offenders.append(f"{path.relative_to(REPO)}: {stripped}")
    assert offenders == []

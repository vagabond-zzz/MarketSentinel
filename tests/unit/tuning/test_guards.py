from __future__ import annotations

import ast
from pathlib import Path

from market_sentinel.cli.main import _build_parser

_FORBIDDEN_FUNCS = {
    "apply_candidate",
    "promote_candidate",
    "activate_snapshot",
    "write_production_config",
    "update_thresholds_from_feedback",
}
_FORBIDDEN_COMMANDS = {"apply", "promote", "activate", "deploy"}


def test_cli_has_no_mutating_tuning_commands() -> None:
    parser = _build_parser()
    tuning = None
    for action in parser._subparsers._group_actions:  # noqa: SLF001
        if getattr(action, "dest", None) == "command":
            tuning = action.choices.get("tuning")
    assert tuning is not None
    inner = None
    for action in tuning._subparsers._group_actions:  # noqa: SLF001
        inner = action.choices
    assert inner is not None
    assert set(inner) == {"snapshot", "compare", "report"}
    assert _FORBIDDEN_COMMANDS.isdisjoint(inner)


def test_tuning_package_has_no_mutation_api() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "market_sentinel" / "tuning"
    names: set[str] = set()
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                names.add(node.name)
    assert _FORBIDDEN_FUNCS.isdisjoint(names)


def test_tuning_sources_do_not_import_dashscope() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "market_sentinel" / "tuning"
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "dashscope" not in text
        assert "IntelligenceCoordinator" not in text

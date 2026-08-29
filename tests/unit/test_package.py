from __future__ import annotations

import json
import tomllib
from pathlib import Path

from market_sentinel import __version__
from market_sentinel.ipc.protocol import PROTOCOL_VERSION
from market_sentinel.tuning.config import (
    OFFLINE_TUNING_CONFIG_ALLOWLIST,
    capture_baseline_config,
    tuning_parameter_inventory,
)
from market_sentinel.tuning.report import TUNING_COMPARISON_SCHEMA_VERSION
from market_sentinel.tuning.store import TUNING_ARTIFACT_SCHEMA_VERSION

_ROOT = Path(__file__).resolve().parents[2]
_RELEASE = "0.6.0"


def test_package_version_matches_pyproject() -> None:
    with (_ROOT / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    assert __version__ == project_version == _RELEASE


def test_package_version_matches_uv_lock_local_package() -> None:
    with (_ROOT / "uv.lock").open("rb") as handle:
        lock = tomllib.load(handle)
    local = next(package for package in lock["package"] if package["name"] == "market-sentinel")
    assert local["version"] == __version__ == _RELEASE


def test_cursor_package_version_matches_python() -> None:
    pkg = json.loads(
        (_ROOT / "apps" / "cursor-extension" / "package.json").read_text(encoding="utf-8")
    )
    assert pkg["version"] == _RELEASE


def test_protocol_and_tuning_schemas_are_independent_of_package_version() -> None:
    assert PROTOCOL_VERSION == 1
    assert TUNING_ARTIFACT_SCHEMA_VERSION == 2
    assert TUNING_COMPARISON_SCHEMA_VERSION == 2
    assert __version__ == _RELEASE
    assert PROTOCOL_VERSION != TUNING_ARTIFACT_SCHEMA_VERSION
    assert PROTOCOL_VERSION != TUNING_COMPARISON_SCHEMA_VERSION


def test_supported_tuning_inventory_is_exactly_seven_evidence_backed_fields() -> None:
    supported = {item.name for item in tuning_parameter_inventory() if item.status == "supported"}
    assert supported == set(OFFLINE_TUNING_CONFIG_ALLOWLIST)
    assert supported == {
        "cluster_lookback_s",
        "hot_event_severity",
        "hot_volume_ratio_5m",
        "hot_change_5m",
        "warm_change_1m",
        "warm_change_5m",
        "warm_volume_ratio",
    }
    assert set(capture_baseline_config().to_record()) == supported


def test_production_runtime_does_not_import_tuning() -> None:
    src = _ROOT / "src" / "market_sentinel"
    for rel in ("runtime/engine.py", "ipc/daemon.py"):
        text = (src / rel).read_text(encoding="utf-8")
        assert "market_sentinel.tuning" not in text
        assert "load_snapshot" not in text

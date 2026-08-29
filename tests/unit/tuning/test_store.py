from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.errors import TuningSnapshotError
from market_sentinel.telemetry.contract import TuningSource
from market_sentinel.tuning.config import capture_baseline_config
from market_sentinel.tuning.store import (
    load_snapshot,
    make_artifact,
    snapshot_path,
    write_snapshot,
)


def test_snapshot_round_trip(tmp_path: Path) -> None:
    clock = FakeClock(wall=1_700_000_000.0)
    artifact = make_artifact(
        capture_baseline_config(),
        config_version="baseline-0.5.0",
        source=TuningSource.OFFLINE_EVAL,
        clock=clock,
    )
    path = write_snapshot(tmp_path, artifact)
    loaded = load_snapshot(tmp_path, artifact.snapshot.snapshot_id)
    assert loaded.snapshot == artifact.snapshot
    assert loaded.config == artifact.config
    assert path == snapshot_path(tmp_path, artifact.snapshot.snapshot_id)
    disk = json.loads(path.read_text(encoding="utf-8"))
    assert disk["schema_version"] == 2
    assert disk["snapshot"]["config_version"] == "baseline-0.5.0"


def test_duplicate_snapshot_id_does_not_overwrite(tmp_path: Path) -> None:
    artifact = make_artifact(
        capture_baseline_config(),
        config_version="baseline-0.5.0",
        source=TuningSource.MANUAL,
    )
    write_snapshot(tmp_path, artifact)
    with pytest.raises(TuningSnapshotError, match="overwrite"):
        write_snapshot(tmp_path, artifact)
    loaded = load_snapshot(tmp_path, artifact.snapshot.snapshot_id)
    assert loaded.snapshot.config_version == "baseline-0.5.0"


def test_unknown_and_free_text_keys_rejected(tmp_path: Path) -> None:
    artifact = make_artifact(
        capture_baseline_config(),
        config_version="baseline-0.5.0",
        source=TuningSource.MANUAL,
    )
    path = write_snapshot(tmp_path, artifact)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["comment"] = "nope"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TuningSnapshotError, match="unknown"):
        load_snapshot(tmp_path, artifact.snapshot.snapshot_id)


def test_config_version_is_not_a_path(tmp_path: Path) -> None:
    artifact = make_artifact(
        capture_baseline_config(),
        config_version="../../etc/passwd",
        source=TuningSource.MANUAL,
    )
    path = write_snapshot(tmp_path, artifact)
    assert path.parent == tmp_path / "tuning"
    assert path.name == f"{artifact.snapshot.snapshot_id}.json"
    assert not (tmp_path / "etc").exists()
    loaded = load_snapshot(tmp_path, artifact.snapshot.snapshot_id)
    assert loaded.snapshot.config_version == "../../etc/passwd"


def test_unsupported_schema_version_fail_closed(tmp_path: Path) -> None:
    artifact = make_artifact(
        capture_baseline_config(),
        config_version="baseline-0.5.0",
        source=TuningSource.MANUAL,
    )
    path = write_snapshot(tmp_path, artifact)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(TuningSnapshotError, match="unsupported tuning artifact schema_version"):
        load_snapshot(tmp_path, artifact.snapshot.snapshot_id)


def test_production_modules_do_not_import_tuning() -> None:
    root = Path(__file__).resolve().parents[3] / "src" / "market_sentinel"
    for rel in (
        "ipc/daemon.py",
        "runtime/engine.py",
        "providers/factory.py",
        "telemetry/factory.py",
        "providers/replay.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "market_sentinel.tuning" not in text
        assert "/tuning/" not in text

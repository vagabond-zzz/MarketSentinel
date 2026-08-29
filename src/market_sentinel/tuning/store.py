from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from market_sentinel.clock import Clock, SystemClock
from market_sentinel.errors import TuningSnapshotError
from market_sentinel.telemetry.contract import (
    TELEMETRY_DENYLIST,
    TUNING_ALLOWLIST,
    TuningSnapshot,
    TuningSource,
)
from market_sentinel.telemetry.paths import resolve_data_dir
from market_sentinel.tuning.config import (
    OFFLINE_TUNING_CONFIG_ALLOWLIST,
    OfflineTuningConfig,
)

TUNING_ARTIFACT_SCHEMA_VERSION = 1
TUNING_DIR_NAME = "tuning"

TUNING_ARTIFACT_TOP_KEYS: frozenset[str] = frozenset({"schema_version", "snapshot", "config"})


@dataclass(frozen=True)
class TuningArtifact:
    """Immutable snapshot file body: identity + OfflineTuningConfig. Not a Runtime load target."""

    snapshot: TuningSnapshot
    config: OfflineTuningConfig
    schema_version: int = TUNING_ARTIFACT_SCHEMA_VERSION

    def to_record(self) -> dict[str, Any]:
        if self.schema_version != TUNING_ARTIFACT_SCHEMA_VERSION:
            raise TuningSnapshotError("unsupported tuning artifact schema_version")
        raw = {
            "schema_version": self.schema_version,
            "snapshot": self.snapshot.to_record(),
            "config": self.config.to_record(),
        }
        denied = TELEMETRY_DENYLIST.intersection(_all_keys(raw))
        if denied:
            raise TuningSnapshotError(f"denied keys: {sorted(denied)}")
        return raw


def _all_keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        found.update(payload)
        for value in payload.values():
            found.update(_all_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            found.update(_all_keys(item))
    return found


def tuning_dir(data_dir: Path) -> Path:
    return data_dir / TUNING_DIR_NAME


def validate_snapshot_id(snapshot_id: str) -> str:
    if not isinstance(snapshot_id, str) or snapshot_id.strip() == "":
        raise TuningSnapshotError("snapshot_id must be non-empty")
    if "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise TuningSnapshotError("snapshot_id is not a filesystem path")
    try:
        parsed = uuid.UUID(hex=snapshot_id)
    except ValueError as exc:
        raise TuningSnapshotError("snapshot_id must be an opaque UUID hex") from exc
    if parsed.hex != snapshot_id:
        raise TuningSnapshotError("snapshot_id must be an opaque UUID hex")
    return snapshot_id


def snapshot_path(data_dir: Path, snapshot_id: str) -> Path:
    return tuning_dir(data_dir) / f"{validate_snapshot_id(snapshot_id)}.json"


def make_artifact(
    config: OfflineTuningConfig,
    *,
    config_version: str,
    source: TuningSource,
    clock: Clock | None = None,
    snapshot_id: str | None = None,
) -> TuningArtifact:
    if not isinstance(config_version, str) or config_version.strip() == "":
        raise TuningSnapshotError("config_version must be non-empty")
    ident = snapshot_id if snapshot_id is not None else uuid.uuid4().hex
    validate_snapshot_id(ident)
    wall = (clock or SystemClock()).wall_time()
    return TuningArtifact(
        snapshot=TuningSnapshot(
            snapshot_id=ident,
            created_timestamp=wall,
            source=source,
            config_version=config_version,
        ),
        config=config,
    )


def write_snapshot(data_dir: Path, artifact: TuningArtifact) -> Path:
    path = snapshot_path(data_dir, artifact.snapshot.snapshot_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise TuningSnapshotError("snapshot_id already exists; refusing to overwrite")
    payload = artifact.to_record()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_snapshot(data_dir: Path, snapshot_id: str) -> TuningArtifact:
    path = snapshot_path(data_dir, snapshot_id)
    if not path.is_file():
        raise TuningSnapshotError("tuning snapshot not found")
    try:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TuningSnapshotError("tuning snapshot is not valid UTF-8 JSON") from exc
    return artifact_from_record(payload)


def artifact_from_record(payload: object) -> TuningArtifact:
    if not isinstance(payload, dict):
        raise TuningSnapshotError("tuning snapshot must be a JSON object")
    extra = set(payload) - TUNING_ARTIFACT_TOP_KEYS
    if extra:
        raise TuningSnapshotError("unknown tuning artifact keys")
    missing = TUNING_ARTIFACT_TOP_KEYS - set(payload)
    if missing:
        raise TuningSnapshotError("missing tuning artifact keys")
    version = payload.get("schema_version")
    if version != TUNING_ARTIFACT_SCHEMA_VERSION:
        raise TuningSnapshotError("unsupported tuning artifact schema_version")
    snapshot_raw = payload.get("snapshot")
    if not isinstance(snapshot_raw, dict):
        raise TuningSnapshotError("snapshot must be an object")
    extra_snap = set(snapshot_raw) - TUNING_ALLOWLIST
    if extra_snap:
        raise TuningSnapshotError("unknown snapshot keys")
    missing_snap = TUNING_ALLOWLIST - set(snapshot_raw)
    if missing_snap:
        raise TuningSnapshotError("missing snapshot keys")
    try:
        source = TuningSource(str(snapshot_raw["source"]))
    except ValueError as exc:
        raise TuningSnapshotError("invalid snapshot source") from exc
    ident = snapshot_raw["snapshot_id"]
    created = snapshot_raw["created_timestamp"]
    version_text = snapshot_raw["config_version"]
    if not isinstance(ident, str):
        raise TuningSnapshotError("invalid snapshot identity")
    if isinstance(created, bool) or not isinstance(created, int | float):
        raise TuningSnapshotError("invalid snapshot identity")
    if not isinstance(version_text, str):
        raise TuningSnapshotError("invalid snapshot identity")
    try:
        snapshot = TuningSnapshot(
            snapshot_id=ident,
            created_timestamp=float(created),
            source=source,
            config_version=version_text,
        )
    except (TypeError, ValueError) as exc:
        raise TuningSnapshotError("invalid snapshot identity") from exc
    validate_snapshot_id(snapshot.snapshot_id)
    config_raw = payload.get("config")
    try:
        config = OfflineTuningConfig.from_record(config_raw)
    except Exception as exc:
        raise TuningSnapshotError("invalid OfflineTuningConfig") from exc
    extra_cfg = (
        set(config_raw) - OFFLINE_TUNING_CONFIG_ALLOWLIST if isinstance(config_raw, dict) else set()
    )
    if extra_cfg:
        raise TuningSnapshotError("unknown config keys")
    return TuningArtifact(snapshot=snapshot, config=config, schema_version=int(version))


def resolve_tuning_data_dir(override: Path | None = None) -> Path:
    return resolve_data_dir(override)

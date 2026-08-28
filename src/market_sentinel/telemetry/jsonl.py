"""Append-only local telemetry JSONL. Not Protocol stdout.

Lifecycle: open (repair trailing partial) → append + flush → rotate → close.

Corruption:
  - Trailing incomplete last line (JSON or UTF-8): reader skips it; next open truncates it.
  - Valid JSON missing a trailing newline: next open appends a newline.
  - Complete malformed line in the middle (invalid UTF-8 or JSON): counted;
    ``healthy`` is False; file is not rewritten.

Rotation: after a write, if size >= max_bytes, close, shift ``.1``..``N`` backups, reopen.
A single record larger than max_bytes is still written (one record may occupy a whole file).

Writes run synchronously on the producer thread (write → flush → stat → maybe rotate).
Storage diagnostics use this module's logger, never the telemetry stream.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from market_sentinel.telemetry.contract import TELEMETRY_ALLOWLIST, project_allowlist

logger = logging.getLogger(__name__)

DEFAULT_MAX_BYTES = 1_048_576
DEFAULT_BACKUP_COUNT = 5


class JsonlTelemetrySink:
    """Append-only UTF-8 JSONL. Rotation is bounded. Not Protocol stdout."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
        allowlist: frozenset[str] | None = None,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be >= 1")
        if backup_count < 1:
            raise ValueError("backup_count must be >= 1")
        self._path = path
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._allowlist = TELEMETRY_ALLOWLIST if allowlist is None else allowlist
        self._handle: TextIO | None = None
        path.parent.mkdir(parents=True, exist_ok=True)
        _truncate_trailing_partial(path)
        self._open()

    def write(self, record: dict[str, object]) -> None:
        payload = project_allowlist(dict(record), self._allowlist)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        handle = self._require()
        handle.write(line + "\n")
        handle.flush()
        if self._path.stat().st_size >= self._max_bytes:
            self._rotate()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def _open(self) -> None:
        self._handle = self._path.open("a", encoding="utf-8", newline="\n")

    def _require(self) -> TextIO:
        if self._handle is None:
            self._open()
        assert self._handle is not None
        return self._handle

    def _rotate(self) -> None:
        self.close()
        oldest = _backup_path(self._path, self._backup_count)
        if oldest.exists():
            oldest.unlink()
        for index in range(self._backup_count - 1, 0, -1):
            source = _backup_path(self._path, index)
            if source.exists():
                source.replace(_backup_path(self._path, index + 1))
        if self._path.exists():
            self._path.replace(_backup_path(self._path, 1))
        self._open()


def _backup_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}")


def rotated_paths(path: Path, backup_count: int) -> tuple[Path, ...]:
    """Oldest backup first, current file last."""
    files = [
        _backup_path(path, index)
        for index in range(backup_count, 0, -1)
        if _backup_path(path, index).exists()
    ]
    if path.exists():
        files.append(path)
    return tuple(files)


def _truncate_trailing_partial(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        return
    last_nl = raw.rfind(b"\n")
    tail = raw[last_nl + 1 :] if last_nl >= 0 else raw
    try:
        json.loads(tail.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("telemetry jsonl truncating trailing incomplete record path=%s", path)
        path.write_bytes(raw[: last_nl + 1] if last_nl >= 0 else b"")
        return
    path.write_bytes(raw + b"\n")


@dataclass(frozen=True)
class JsonlReadResult:
    records: list[dict[str, object]]
    skipped_trailing_partial: bool
    malformed_complete_lines: int

    @property
    def healthy(self) -> bool:
        return self.malformed_complete_lines == 0


def read_jsonl(path: Path) -> JsonlReadResult:
    """Read one JSONL file.

    Complete newline-terminated lines are decoded one at a time. Invalid UTF-8 or
    JSON on a complete line is corruption (``healthy`` is False), not an exception.
    A trailing fragment without a newline is skipped, not counted as middle corruption.
    """
    if not path.exists():
        return JsonlReadResult([], False, 0)
    raw = path.read_bytes()
    skipped_trailing = False
    complete = raw
    extra_complete: bytes | None = None
    if raw and not raw.endswith(b"\n"):
        last_nl = raw.rfind(b"\n")
        prefix = raw[: last_nl + 1] if last_nl >= 0 else b""
        tail = raw[last_nl + 1 :] if last_nl >= 0 else raw
        try:
            json.loads(tail.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            skipped_trailing = True
            complete = prefix
        else:
            complete = prefix
            extra_complete = tail
    records: list[dict[str, object]] = []
    malformed = 0
    lines = _newline_terminated_lines(complete)
    if extra_complete is not None:
        lines.append(extra_complete)
    for line in lines:
        if line.strip() == b"":
            continue
        try:
            text = line.decode("utf-8")
        except UnicodeDecodeError:
            malformed += 1
            logger.warning("telemetry jsonl malformed utf-8 complete line in %s", path)
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            malformed += 1
            logger.warning("telemetry jsonl malformed complete line in %s", path)
            continue
        if not isinstance(parsed, dict):
            malformed += 1
            logger.warning("telemetry jsonl non-object line in %s", path)
            continue
        records.append(parsed)
    if malformed:
        logger.warning(
            "telemetry jsonl corruption path=%s malformed_complete_lines=%s",
            path,
            malformed,
        )
    return JsonlReadResult(records, skipped_trailing, malformed)


def _newline_terminated_lines(blob: bytes) -> list[bytes]:
    if not blob:
        return []
    parts = blob.split(b"\n")
    if blob.endswith(b"\n"):
        return parts[:-1]
    return parts

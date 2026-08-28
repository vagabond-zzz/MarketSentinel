from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from market_sentinel.telemetry.jsonl import DEFAULT_BACKUP_COUNT, read_jsonl, rotated_paths


@dataclass(frozen=True)
class LoadedTelemetry:
    records: tuple[dict[str, object], ...]
    input_files: tuple[str, ...]
    records_read: int
    malformed_complete_lines: int
    skipped_trailing_partial: bool
    healthy: bool


class TelemetryReader:
    """Single JSONL query boundary for evaluation. Oldest rotated file first."""

    def load(self, path: Path, *, backup_count: int = DEFAULT_BACKUP_COUNT) -> LoadedTelemetry:
        files = rotated_paths(path, backup_count)
        records: list[dict[str, object]] = []
        malformed = 0
        skipped = False
        names: list[str] = []
        for file in files:
            names.append(str(file))
            result = read_jsonl(file)
            records.extend(result.records)
            malformed += result.malformed_complete_lines
            skipped = skipped or result.skipped_trailing_partial
        return LoadedTelemetry(
            records=tuple(records),
            input_files=tuple(names),
            records_read=len(records),
            malformed_complete_lines=malformed,
            skipped_trailing_partial=skipped,
            healthy=malformed == 0,
        )

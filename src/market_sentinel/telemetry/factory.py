from __future__ import annotations

import logging
from pathlib import Path

from market_sentinel.clock import Clock
from market_sentinel.telemetry.collector import NoOpTelemetryCollector, SinkTelemetryCollector
from market_sentinel.telemetry.jsonl import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    JsonlTelemetrySink,
)
from market_sentinel.telemetry.paths import resolve_data_dir, telemetry_jsonl_path
from market_sentinel.telemetry.runtime import TelemetryRuntime

logger = logging.getLogger(__name__)


def jsonl_telemetry_runtime(
    clock: Clock,
    *,
    data_dir: Path | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> TelemetryRuntime:
    directory = resolve_data_dir(data_dir)
    try:
        sink = JsonlTelemetrySink(
            telemetry_jsonl_path(directory),
            max_bytes=DEFAULT_MAX_BYTES if max_bytes is None else max_bytes,
            backup_count=DEFAULT_BACKUP_COUNT if backup_count is None else backup_count,
        )
        collector: SinkTelemetryCollector | NoOpTelemetryCollector = SinkTelemetryCollector(sink)
    except Exception:
        logger.exception(
            "telemetry jsonl sink unavailable under %s; continuing without persistence",
            directory,
        )
        collector = NoOpTelemetryCollector()
    return TelemetryRuntime(clock, collector)

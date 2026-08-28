from __future__ import annotations

import logging
from pathlib import Path

from market_sentinel.clock import Clock
from market_sentinel.telemetry.collector import (
    NoOpFeedbackCollector,
    NoOpTelemetryCollector,
    SinkFeedbackCollector,
    SinkTelemetryCollector,
)
from market_sentinel.telemetry.contract import FEEDBACK_ALLOWLIST, UserFeedback
from market_sentinel.telemetry.jsonl import (
    DEFAULT_BACKUP_COUNT,
    DEFAULT_MAX_BYTES,
    JsonlTelemetrySink,
)
from market_sentinel.telemetry.paths import (
    feedback_jsonl_path,
    resolve_data_dir,
    telemetry_jsonl_path,
)
from market_sentinel.telemetry.runtime import TelemetryRuntime

logger = logging.getLogger(__name__)


class _LazyJsonlFeedbackCollector:
    """Open feedback.jsonl on first explicit record. Host/CLI never see this path."""

    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int,
        backup_count: int,
    ) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._inner: SinkFeedbackCollector | None = None

    def record(self, feedback: UserFeedback) -> None:
        if self._inner is None:
            sink = JsonlTelemetrySink(
                self._path,
                max_bytes=self._max_bytes,
                backup_count=self._backup_count,
                allowlist=FEEDBACK_ALLOWLIST,
            )
            self._inner = SinkFeedbackCollector(sink)
        self._inner.record(feedback)

    def close(self) -> None:
        if self._inner is None:
            return
        self._inner.close()
        self._inner = None


def jsonl_telemetry_runtime(
    clock: Clock,
    *,
    data_dir: Path | None = None,
    max_bytes: int | None = None,
    backup_count: int | None = None,
) -> TelemetryRuntime:
    directory = resolve_data_dir(data_dir)
    size = DEFAULT_MAX_BYTES if max_bytes is None else max_bytes
    backups = DEFAULT_BACKUP_COUNT if backup_count is None else backup_count
    try:
        sink = JsonlTelemetrySink(
            telemetry_jsonl_path(directory),
            max_bytes=size,
            backup_count=backups,
        )
        collector: SinkTelemetryCollector | NoOpTelemetryCollector = SinkTelemetryCollector(sink)
    except Exception:
        logger.exception(
            "telemetry jsonl sink unavailable under %s; continuing without persistence",
            directory,
        )
        collector = NoOpTelemetryCollector()
    try:
        feedback: _LazyJsonlFeedbackCollector | NoOpFeedbackCollector = _LazyJsonlFeedbackCollector(
            feedback_jsonl_path(directory),
            max_bytes=size,
            backup_count=backups,
        )
    except Exception:
        logger.exception(
            "feedback jsonl sink unavailable under %s; continuing without feedback persistence",
            directory,
        )
        feedback = NoOpFeedbackCollector()
    return TelemetryRuntime(clock, collector, feedback=feedback)

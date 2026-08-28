from __future__ import annotations

import logging
from typing import Protocol

from market_sentinel.telemetry.contract import TelemetryEvent

logger = logging.getLogger(__name__)


class TelemetryCollector(Protocol):
    """Append-only observation sink. Producers must not import storage backends."""

    def record(self, event: TelemetryEvent) -> None: ...


class NoOpTelemetryCollector:
    def record(self, event: TelemetryEvent) -> None:
        del event


class InMemoryTelemetryCollector:
    def __init__(self) -> None:
        self.events: list[TelemetryEvent] = []

    def record(self, event: TelemetryEvent) -> None:
        self.events.append(event)


class FailOpenTelemetryCollector:
    """Collector failures must not break the market pipeline."""

    def __init__(self, inner: TelemetryCollector) -> None:
        self._inner = inner

    def record(self, event: TelemetryEvent) -> None:
        try:
            self._inner.record(event)
        except Exception:
            logger.exception("telemetry collector failed; market pipeline continues")

    def close(self) -> None:
        closer = getattr(self._inner, "close", None)
        if not callable(closer):
            return
        try:
            closer()
        except Exception:
            logger.exception("telemetry collector close failed")

from __future__ import annotations

import logging
import uuid
from typing import Any

from market_sentinel.clock import Clock
from market_sentinel.telemetry.collector import (
    FailOpenTelemetryCollector,
    NoOpTelemetryCollector,
    TelemetryCollector,
)
from market_sentinel.telemetry.contract import (
    ClusterMembershipTracker,
    TelemetryEvent,
    TelemetryName,
    kind_for,
)

logger = logging.getLogger(__name__)


def new_run_id() -> str:
    """Opaque id for one Core runtime / Replay execution. Not a market session date."""
    return uuid.uuid4().hex


class TelemetryRuntime:
    """Per-execution telemetry context. Not part of MarketState."""

    def __init__(
        self,
        clock: Clock,
        collector: TelemetryCollector | None = None,
        *,
        run_id: str | None = None,
    ) -> None:
        self.clock = clock
        self.run_id = run_id if run_id is not None and run_id.strip() != "" else new_run_id()
        inner = collector if collector is not None else NoOpTelemetryCollector()
        self.collector: TelemetryCollector = FailOpenTelemetryCollector(inner)
        self.cluster = ClusterMembershipTracker()

    def emit(self, name: TelemetryName, **fields: Any) -> None:
        created = fields.pop("created_timestamp", self.clock.wall_time())
        try:
            event = TelemetryEvent(
                telemetry_id=uuid.uuid4().hex,
                name=name,
                kind=kind_for(name),
                created_timestamp=created,
                run_id=self.run_id,
                **fields,
            )
            self.collector.record(event)
        except Exception:
            logger.exception("telemetry emit failed; market pipeline continues")

    def close(self) -> None:
        closer = getattr(self.collector, "close", None)
        if callable(closer):
            closer()

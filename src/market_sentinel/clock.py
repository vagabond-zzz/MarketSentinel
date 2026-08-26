from __future__ import annotations

import time
from typing import Protocol


class Clock(Protocol):
    def wall_time(self) -> float:
        """Unix epoch seconds for market/received timestamps and feed latency."""

    def monotonic_time(self) -> float:
        """Elapsed seconds for intervals, dwell, timeouts, and age."""


class SystemClock:
    def wall_time(self) -> float:
        return time.time()

    def monotonic_time(self) -> float:
        return time.monotonic()


class FakeClock:
    def __init__(self, wall: float = 1_700_000_000.0, monotonic: float = 0.0) -> None:
        self._wall = wall
        self._mono = monotonic

    def wall_time(self) -> float:
        return self._wall

    def monotonic_time(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._wall += seconds
        self._mono += seconds

    def set_wall(self, timestamp: float) -> None:
        self._wall = timestamp

    def advance_wall(self, seconds: float) -> None:
        self._wall += seconds

    def advance_monotonic(self, seconds: float) -> None:
        self._mono += seconds

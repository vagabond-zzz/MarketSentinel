from __future__ import annotations

import logging

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import SchedulerLevel
from market_sentinel.errors import InvalidSchedulerLevelError
from market_sentinel.scheduler.policy import SchedulerPolicy

logger = logging.getLogger(__name__)

_RANK = {
    SchedulerLevel.COLD: 0,
    SchedulerLevel.WARM: 1,
    SchedulerLevel.HOT: 2,
}


class AdaptiveScheduler:
    def __init__(self, clock: Clock, policy: SchedulerPolicy | None = None) -> None:
        self._clock = clock
        self._policy = policy or SchedulerPolicy()
        self._levels: dict[str, SchedulerLevel] = {}
        self._last_change_mono: dict[str, float] = {}
        self._last_fetch_mono: dict[str, float] = {}

    def get_level(self, symbol: str) -> SchedulerLevel:
        return self._levels.get(symbol, SchedulerLevel.COLD)

    def set_level(self, symbol: str, level: SchedulerLevel, *, force: bool = False) -> bool:
        if not isinstance(level, SchedulerLevel):
            raise InvalidSchedulerLevelError(f"invalid scheduler level: {level!r}")

        current = self.get_level(symbol)
        if level is current:
            self._levels.setdefault(symbol, current)
            return True

        if not force and not self._dwell_elapsed(symbol, current, level):
            return False

        self._levels[symbol] = level
        self._last_change_mono[symbol] = self._clock.monotonic_time()
        logger.info("scheduler %s %s -> %s", symbol, current.value, level.value)
        return True

    def due_symbols(self, symbols: list[str]) -> list[str]:
        now = self._clock.monotonic_time()
        due: list[str] = []
        for symbol in symbols:
            last_fetch = self._last_fetch_mono.get(symbol)
            if last_fetch is None or now - last_fetch >= self._interval(self.get_level(symbol)):
                due.append(symbol)
        return due

    def mark_fetched(self, symbol: str) -> None:
        self._last_fetch_mono[symbol] = self._clock.monotonic_time()

    def next_wait_s(self, symbols: list[str]) -> float:
        if not symbols:
            return 1.0
        now = self._clock.monotonic_time()
        remaining: list[float] = []
        for symbol in symbols:
            last_fetch = self._last_fetch_mono.get(symbol)
            interval = self._interval(self.get_level(symbol))
            if last_fetch is None:
                remaining.append(0.0)
                continue
            remaining.append(max(0.0, interval - (now - last_fetch)))
        return min(remaining)

    def _interval(self, level: SchedulerLevel) -> float:
        if level is SchedulerLevel.HOT:
            return self._policy.hot_interval_s
        if level is SchedulerLevel.WARM:
            return self._policy.warm_interval_s
        return self._policy.cold_interval_s

    def _dwell_elapsed(
        self,
        symbol: str,
        current: SchedulerLevel,
        target: SchedulerLevel,
    ) -> bool:
        required = self._required_dwell(current, target)
        last_change = self._last_change_mono.get(symbol)
        if last_change is None:
            return True
        return self._clock.monotonic_time() - last_change >= required

    def _required_dwell(self, current: SchedulerLevel, target: SchedulerLevel) -> float:
        if _RANK[target] > _RANK[current]:
            return self._policy.upgrade_dwell_s
        if current is SchedulerLevel.HOT:
            return self._policy.hot_downgrade_dwell_s
        return self._policy.warm_downgrade_dwell_s

from __future__ import annotations

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import SignalPriority

_PRIORITY_RANK = {
    SignalPriority.INFO: 1,
    SignalPriority.NOTICE: 2,
    SignalPriority.IMPORTANT: 3,
    SignalPriority.CRITICAL: 4,
}


class CooldownGate:
    """Per-symbol, per-signal-family cooldown on the monotonic clock.

    Same or lower priority inside the cooldown is suppressed. A strictly
    higher priority escalates and resets the cooldown window.
    """

    def __init__(self, clock: Clock, cooldown_s: float = 300.0) -> None:
        self._clock = clock
        self._cooldown_s = cooldown_s
        self._last: dict[tuple[str, str], tuple[float, SignalPriority]] = {}

    def allow(self, symbol: str, family: str, priority: SignalPriority) -> bool:
        now = self._clock.monotonic_time()
        key = (symbol, family)
        previous = self._last.get(key)
        if previous is None:
            self._last[key] = (now, priority)
            return True
        last_mono, last_priority = previous
        if now - last_mono >= self._cooldown_s:
            self._last[key] = (now, priority)
            return True
        if _PRIORITY_RANK[priority] > _PRIORITY_RANK[last_priority]:
            self._last[key] = (now, priority)
            return True
        return False

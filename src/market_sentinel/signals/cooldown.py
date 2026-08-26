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
    """Per-signal-episode cooldown on the monotonic clock.

    Identity is ``signal.id``. A finished episode must not suppress the first
    alert of a new episode, even when symbol/family/priority match.
    """

    def __init__(self, clock: Clock, cooldown_s: float = 300.0) -> None:
        self._clock = clock
        self._cooldown_s = cooldown_s
        self._last: dict[str, tuple[float, SignalPriority]] = {}

    def allow(self, signal_id: str, priority: SignalPriority) -> bool:
        now = self._clock.monotonic_time()
        previous = self._last.get(signal_id)
        if previous is None:
            self._last[signal_id] = (now, priority)
            return True
        last_mono, last_priority = previous
        if now - last_mono >= self._cooldown_s:
            self._last[signal_id] = (now, priority)
            return True
        if _PRIORITY_RANK[priority] > _PRIORITY_RANK[last_priority]:
            self._last[signal_id] = (now, priority)
            return True
        return False

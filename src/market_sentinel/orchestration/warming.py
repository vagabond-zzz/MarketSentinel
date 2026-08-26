from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from market_sentinel.domain.enums import EventType, SchedulerLevel
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures

HOT_EVENT_SEVERITY = 3
HOT_VOLUME_RATIO_5M = 2.0
HOT_CHANGE_5M = 0.012
WARM_CHANGE_1M = 0.004
WARM_CHANGE_5M = 0.008
WARM_VOLUME_RATIO = 1.5

_BREAKOUT_TYPES = frozenset({EventType.DAY_HIGH_BREAKOUT, EventType.DAY_LOW_BREAKDOWN})


@dataclass(frozen=True)
class LevelRequest:
    symbol: str
    level: SchedulerLevel
    reason: str


class WarmingPolicy:
    """Map current features/events to a scheduler attention request.

    Notification cooldown is not an input. A suppressed alert must not
    force a downgrade while the market condition is still abnormal.
    """

    def request(
        self,
        symbol: str,
        features: MarketFeatures | None,
        events: Sequence[MarketEvent],
    ) -> LevelRequest:
        if _is_hot(features, events):
            return LevelRequest(symbol=symbol, level=SchedulerLevel.HOT, reason="strong")
        if _is_warm(features):
            return LevelRequest(symbol=symbol, level=SchedulerLevel.WARM, reason="precursor")
        return LevelRequest(symbol=symbol, level=SchedulerLevel.COLD, reason="quiet")


def _is_hot(features: MarketFeatures | None, events: Sequence[MarketEvent]) -> bool:
    if any(item.severity >= HOT_EVENT_SEVERITY for item in events):
        return True
    if any(item.type in _BREAKOUT_TYPES for item in events):
        return True
    if features is None:
        return False
    if features.volume_ratio_5m is not None and features.volume_ratio_5m >= HOT_VOLUME_RATIO_5M:
        return True
    if features.change_5m is not None and abs(features.change_5m) >= HOT_CHANGE_5M:
        return True
    if (
        features.session_high_ref is not None
        and features.session_high_obs > features.session_high_ref
    ):
        return True
    if features.session_low_ref is not None and features.session_low_obs < features.session_low_ref:
        return True
    return False


def _is_warm(features: MarketFeatures | None) -> bool:
    if features is None:
        return False
    if features.change_1m is not None and abs(features.change_1m) >= WARM_CHANGE_1M:
        return True
    if features.change_5m is not None and abs(features.change_5m) >= WARM_CHANGE_5M:
        return True
    if features.volume_ratio_1m is not None and features.volume_ratio_1m >= WARM_VOLUME_RATIO:
        return True
    if features.volume_ratio_5m is not None and features.volume_ratio_5m >= WARM_VOLUME_RATIO:
        return True
    return False

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
class WarmingConfig:
    """WARM/HOT entry thresholds. Defaults are current production constants."""

    hot_event_severity: int = HOT_EVENT_SEVERITY
    hot_volume_ratio_5m: float = HOT_VOLUME_RATIO_5M
    hot_change_5m: float = HOT_CHANGE_5M
    warm_change_1m: float = WARM_CHANGE_1M
    warm_change_5m: float = WARM_CHANGE_5M
    warm_volume_ratio: float = WARM_VOLUME_RATIO


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

    def __init__(self, config: WarmingConfig | None = None) -> None:
        self._config = config or WarmingConfig()

    def request(
        self,
        symbol: str,
        features: MarketFeatures | None,
        events: Sequence[MarketEvent],
    ) -> LevelRequest:
        if self._is_hot(features, events):
            return LevelRequest(symbol=symbol, level=SchedulerLevel.HOT, reason="strong")
        if self._is_warm(features):
            return LevelRequest(symbol=symbol, level=SchedulerLevel.WARM, reason="precursor")
        return LevelRequest(symbol=symbol, level=SchedulerLevel.COLD, reason="quiet")

    def _is_hot(self, features: MarketFeatures | None, events: Sequence[MarketEvent]) -> bool:
        cfg = self._config
        if any(item.severity >= cfg.hot_event_severity for item in events):
            return True
        if any(item.type in _BREAKOUT_TYPES for item in events):
            return True
        if features is None:
            return False
        if (
            features.volume_ratio_5m is not None
            and features.volume_ratio_5m >= cfg.hot_volume_ratio_5m
        ):
            return True
        if features.change_5m is not None and abs(features.change_5m) >= cfg.hot_change_5m:
            return True
        if (
            features.session_high_ref is not None
            and features.session_high_obs > features.session_high_ref
        ):
            return True
        if (
            features.session_low_ref is not None
            and features.session_low_obs < features.session_low_ref
        ):
            return True
        return False

    def _is_warm(self, features: MarketFeatures | None) -> bool:
        cfg = self._config
        if features is None:
            return False
        if features.change_1m is not None and abs(features.change_1m) >= cfg.warm_change_1m:
            return True
        if features.change_5m is not None and abs(features.change_5m) >= cfg.warm_change_5m:
            return True
        if (
            features.volume_ratio_1m is not None
            and features.volume_ratio_1m >= cfg.warm_volume_ratio
        ):
            return True
        if (
            features.volume_ratio_5m is not None
            and features.volume_ratio_5m >= cfg.warm_volume_ratio
        ):
            return True
        return False

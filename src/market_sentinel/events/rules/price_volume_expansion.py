from __future__ import annotations

from market_sentinel.domain.enums import EventType
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events.rules.common import (
    build_event,
    move_direction,
    rapid_move_severity,
    volume_spike_severity,
)
from market_sentinel.events.thresholds import TTL_LONG_S


class PriceVolumeExpansionRule:
    name = EventType.PRICE_VOLUME_EXPANSION.value

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
        *,
        detected_at: float,
    ) -> list[MarketEvent]:
        del previous
        move = rapid_move_severity(current.change_1m, current.change_5m)
        volume = volume_spike_severity(current.volume_ratio_1m, current.volume_ratio_5m)
        if move is None or volume is None or move < 2 or volume < 2:
            return []
        severity = min(5, max(move, volume) + 1)
        direction = move_direction(current.change_1m, current.change_5m, move)
        return [
            build_event(
                current=current,
                event_type=EventType.PRICE_VOLUME_EXPANSION,
                direction=direction,
                severity=severity,
                detected_at=detected_at,
                metrics={
                    "change_1m": current.change_1m,
                    "change_5m": current.change_5m,
                    "volume_ratio_1m": current.volume_ratio_1m,
                    "volume_ratio_5m": current.volume_ratio_5m,
                    "move_severity": float(move),
                    "volume_severity": float(volume),
                },
                ttl_s=TTL_LONG_S,
                rule_name=self.name,
            )
        ]

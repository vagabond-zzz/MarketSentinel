from __future__ import annotations

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events.rules.common import build_event
from market_sentinel.events.thresholds import TTL_SHORT_S, VWAP_CROSS_SEV3_5M


class VwapCrossRule:
    name = EventType.VWAP_CROSS.value

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
        *,
        detected_at: float,
    ) -> list[MarketEvent]:
        if previous is None:
            return []
        if previous.above_vwap is None or current.above_vwap is None or current.vwap is None:
            return []
        if previous.above_vwap == current.above_vwap:
            return []
        direction = EventDirection.UP if current.above_vwap else EventDirection.DOWN
        severity = 2
        if current.change_5m is not None and abs(current.change_5m) >= VWAP_CROSS_SEV3_5M:
            severity = 3
        return [
            build_event(
                current=current,
                event_type=EventType.VWAP_CROSS,
                direction=direction,
                severity=severity,
                detected_at=detected_at,
                metrics={
                    "vwap": current.vwap,
                    "above_vwap": current.above_vwap,
                    "change_5m": current.change_5m,
                },
                ttl_s=TTL_SHORT_S,
                rule_name=self.name,
            )
        ]

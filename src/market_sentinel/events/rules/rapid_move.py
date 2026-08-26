from __future__ import annotations

from market_sentinel.domain.enums import EventType
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events.rules.common import build_event, move_direction, rapid_move_severity
from market_sentinel.events.thresholds import TTL_SHORT_S


class RapidMoveRule:
    name = EventType.RAPID_MOVE.value

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
        *,
        detected_at: float,
    ) -> list[MarketEvent]:
        del previous
        severity = rapid_move_severity(current.change_1m, current.change_5m)
        if severity is None:
            return []
        direction = move_direction(current.change_1m, current.change_5m, severity)
        return [
            build_event(
                current=current,
                event_type=EventType.RAPID_MOVE,
                direction=direction,
                severity=severity,
                detected_at=detected_at,
                metrics={"change_1m": current.change_1m, "change_5m": current.change_5m},
                ttl_s=TTL_SHORT_S,
                rule_name=self.name,
            )
        ]

from __future__ import annotations

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events.rules.common import breakout_severity, build_event
from market_sentinel.events.thresholds import TTL_SHORT_S


class DayHighBreakoutRule:
    name = EventType.DAY_HIGH_BREAKOUT.value

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
        *,
        detected_at: float,
    ) -> list[MarketEvent]:
        del previous
        ref = current.session_high_ref
        if ref is None or ref <= 0:
            return []
        obs = current.session_high_obs
        if obs <= ref:
            return []
        excess = (obs - ref) / ref
        return [
            build_event(
                current=current,
                event_type=EventType.DAY_HIGH_BREAKOUT,
                direction=EventDirection.UP,
                severity=breakout_severity(excess),
                detected_at=detected_at,
                metrics={
                    "session_high_ref": ref,
                    "session_high_obs": obs,
                    "excess": excess,
                },
                ttl_s=TTL_SHORT_S,
                rule_name=self.name,
            )
        ]

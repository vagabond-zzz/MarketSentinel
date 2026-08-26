from __future__ import annotations

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events.rules.common import build_event, volume_spike_severity
from market_sentinel.events.thresholds import TTL_LONG_S


class VolumeSpikeRule:
    name = EventType.VOLUME_SPIKE.value

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
        *,
        detected_at: float,
    ) -> list[MarketEvent]:
        del previous
        severity = volume_spike_severity(current.volume_ratio_1m, current.volume_ratio_5m)
        if severity is None:
            return []
        return [
            build_event(
                current=current,
                event_type=EventType.VOLUME_SPIKE,
                direction=EventDirection.NONE,
                severity=severity,
                detected_at=detected_at,
                metrics={
                    "volume_ratio_1m": current.volume_ratio_1m,
                    "volume_ratio_5m": current.volume_ratio_5m,
                },
                ttl_s=TTL_LONG_S,
                rule_name=self.name,
            )
        ]

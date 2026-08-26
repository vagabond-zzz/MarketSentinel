from __future__ import annotations

from collections.abc import Sequence

from market_sentinel.clock import Clock
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.events.rules import default_rules
from market_sentinel.events.rules.base import EventRule


class EventDetector:
    def __init__(
        self,
        clock: Clock,
        rules: Sequence[EventRule] | None = None,
    ) -> None:
        self._clock = clock
        self._rules = tuple(rules) if rules is not None else default_rules()

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
    ) -> list[MarketEvent]:
        detected_at = self._clock.wall_time()
        events: list[MarketEvent] = []
        for rule in self._rules:
            events.extend(rule.evaluate(previous, current, detected_at=detected_at))
        return events

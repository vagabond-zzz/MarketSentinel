from __future__ import annotations

from typing import Protocol

from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures


class EventRule(Protocol):
    name: str

    def evaluate(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
        *,
        detected_at: float,
    ) -> list[MarketEvent]: ...

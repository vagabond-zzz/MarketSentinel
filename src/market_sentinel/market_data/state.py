from __future__ import annotations

from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.models import MarketSnapshot, MarketState


class MarketStateStore:
    def __init__(self) -> None:
        self._states: dict[str, MarketState] = {}

    def get(self, symbol: str) -> MarketState | None:
        return self._states.get(symbol)

    def update_latest(self, snapshot: MarketSnapshot) -> MarketState:
        current = self._states.get(snapshot.symbol)
        state = MarketState(
            symbol=snapshot.symbol,
            latest=snapshot,
            level=current.level if current is not None else SchedulerLevel.COLD,
            feed_status=current.feed_status if current is not None else FeedStatus.LIVE,
            feed_latency=current.feed_latency if current is not None else None,
            last_update_age=current.last_update_age if current is not None else None,
        )
        self._states[snapshot.symbol] = state
        return state

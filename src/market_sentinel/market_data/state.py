from __future__ import annotations

from typing import Any

from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.models import MarketSnapshot, MarketState
from market_sentinel.domain.signals import Signal

_UNSET: Any = object()


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
            features=current.features if current is not None else None,
            active_signals=current.active_signals if current is not None else (),
        )
        self._states[snapshot.symbol] = state
        return state

    def apply_runtime(
        self,
        symbol: str,
        *,
        level: SchedulerLevel,
        feed_status: FeedStatus,
        feed_latency: float | None,
        last_update_age: float | None,
        features: MarketFeatures | None | object = _UNSET,
        active_signals: tuple[Signal, ...] | object = _UNSET,
    ) -> MarketState:
        current = self._states.get(symbol)
        if features is _UNSET:
            resolved_features = current.features if current is not None else None
        else:
            resolved_features = features  # type: ignore[assignment]
        if active_signals is _UNSET:
            resolved_signals = current.active_signals if current is not None else ()
        else:
            resolved_signals = active_signals  # type: ignore[assignment]
        state = MarketState(
            symbol=symbol,
            latest=current.latest if current is not None else None,
            level=level,
            feed_status=feed_status,
            feed_latency=feed_latency,
            last_update_age=last_update_age,
            features=resolved_features,
            active_signals=resolved_signals,
        )
        self._states[symbol] = state
        return state

    def snapshot_for(self, symbols: list[str]) -> list[MarketState]:
        return [self._states[symbol] for symbol in symbols if symbol in self._states]

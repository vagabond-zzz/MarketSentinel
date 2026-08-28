from __future__ import annotations

from collections.abc import Callable

from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.models import MarketState
from market_sentinel.domain.signals import Signal
from market_sentinel.intelligence.contract import (
    FallbackReason,
    IntelligenceResult,
    IntelligenceStatus,
)
from market_sentinel.intelligence.view import intelligence_view
from market_sentinel.ipc.dto import (
    WireAlertCandidate,
    WireIntelligence,
    WireMarketState,
    WireSignal,
    WireSymbolState,
)
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult


def map_intelligence(result: IntelligenceResult | None, signal_id: str) -> WireIntelligence | None:
    view = intelligence_view(result, signal_id)
    if view.status is IntelligenceStatus.NOT_REQUESTED:
        return None
    annotation = view.annotation
    fallback = None if view.fallback_reason is FallbackReason.NONE else view.fallback_reason.value
    return WireIntelligence(
        status=view.status.value,
        summary=None if annotation is None else annotation.summary,
        reason=None if annotation is None else annotation.reason,
        confidence=None if annotation is None else annotation.confidence,
        fallback_reason=fallback,
        worth_highlight=None if annotation is None else annotation.worth_highlight,
    )


def map_signal(signal: Signal, intelligence: IntelligenceResult | None = None) -> WireSignal:
    return WireSignal(
        id=signal.id,
        family=signal.family,
        direction=signal.direction.value,
        priority=signal.priority.value,
        title=signal.title,
        summary=signal.summary,
        intelligence=map_intelligence(intelligence, signal.id),
    )


def map_alert_candidate(signal: Signal) -> WireAlertCandidate:
    return WireAlertCandidate(
        id=signal.id,
        symbol=signal.symbol,
        family=signal.family,
        direction=signal.direction.value,
        priority=signal.priority.value,
        title=signal.title,
        summary=signal.summary,
    )


def map_symbol_state(
    symbol: str,
    state: MarketState | None,
    *,
    intelligence_of: Callable[[str], IntelligenceResult | None] | None = None,
) -> WireSymbolState:
    features: MarketFeatures | None = None if state is None else state.features
    latest = None if state is None else state.latest
    return WireSymbolState(
        symbol=symbol,
        price=None if latest is None else latest.price,
        scheduler_level=(SchedulerLevel.COLD.value if state is None else state.level.value),
        feed_status=(FeedStatus.DISCONNECTED.value if state is None else state.feed_status.value),
        change_1m=None if features is None else features.change_1m,
        change_5m=None if features is None else features.change_5m,
        change_15m=None if features is None else features.change_15m,
        volume_ratio_1m=None if features is None else features.volume_ratio_1m,
        volume_ratio_5m=None if features is None else features.volume_ratio_5m,
        ema5=None if features is None else features.ema5,
        ema20=None if features is None else features.ema20,
        rsi14=None if features is None else features.rsi14,
        vwap=None if features is None else features.vwap,
        active_signals=(
            ()
            if state is None
            else tuple(
                map_signal(
                    item,
                    None if intelligence_of is None else intelligence_of(item.id),
                )
                for item in state.active_signals
            )
        ),
    )


def map_engine_state(engine: MarketEngine) -> WireMarketState:
    items = engine.watchlist.list()
    registry = None if engine.intelligence is None else engine.intelligence.registry

    def lookup(signal_id: str) -> IntelligenceResult | None:
        if registry is None:
            return None
        return registry.get(signal_id)

    symbols = tuple(
        map_symbol_state(item.symbol, engine.states.get(item.symbol), intelligence_of=lookup)
        for item in items
    )
    enabled = engine.watchlist.enabled_symbols()
    feed = engine.health.aggregate_status(enabled) if enabled else FeedStatus.DISCONNECTED
    return WireMarketState(
        watchlist_count=len(items),
        feed_status=feed.value,
        symbols=symbols,
    )


def map_tick_alerts(
    result: EngineTickResult,
) -> tuple[tuple[WireAlertCandidate, ...], float | None]:
    candidates: list[WireAlertCandidate] = []
    market_timestamp: float | None = None
    for symbol_result in result.symbol_results:
        for signal in symbol_result.alert_candidates:
            candidates.append(map_alert_candidate(signal))
            market_timestamp = signal.market_timestamp
    return tuple(candidates), market_timestamp

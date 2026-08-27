from __future__ import annotations

from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.models import MarketState
from market_sentinel.domain.signals import Signal
from market_sentinel.ipc.dto import WireAlertCandidate, WireMarketState, WireSignal, WireSymbolState
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult


def map_signal(signal: Signal) -> WireSignal:
    return WireSignal(
        id=signal.id,
        family=signal.family,
        direction=signal.direction.value,
        priority=signal.priority.value,
        title=signal.title,
        summary=signal.summary,
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


def map_symbol_state(symbol: str, state: MarketState | None) -> WireSymbolState:
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
            () if state is None else tuple(map_signal(item) for item in state.active_signals)
        ),
    )


def map_engine_state(engine: MarketEngine) -> WireMarketState:
    items = engine.watchlist.list()
    symbols = tuple(map_symbol_state(item.symbol, engine.states.get(item.symbol)) for item in items)
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

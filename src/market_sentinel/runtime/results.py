from __future__ import annotations

from dataclasses import dataclass

from market_sentinel.domain.enums import SchedulerLevel
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import Signal, SignalTrace


@dataclass(frozen=True)
class SymbolTickResult:
    """Edge-triggered output for one symbol on one tick."""

    symbol: str
    features: MarketFeatures | None
    accepted_events: tuple[MarketEvent, ...]
    signal_updates: tuple[Signal, ...]
    traces: tuple[SignalTrace, ...]
    alert_candidates: tuple[Signal, ...]
    level_before: SchedulerLevel
    level_after: SchedulerLevel


@dataclass(frozen=True)
class EngineTickResult:
    """This tick's new output. Durable state lives on MarketState."""

    symbol_results: tuple[SymbolTickResult, ...]

    def for_symbol(self, symbol: str) -> SymbolTickResult | None:
        for item in self.symbol_results:
            if item.symbol == symbol:
                return item
        return None

"""Read-only capability facade over a running MarketEngine.

Capabilities are the stable boundary between Core and host layers (CLI today,
an MCP server in a later milestone). Rules of the layer:

- read-only: no capability mutates watchlist, scheduler, provider, intelligence
  configuration, tuning, or any core state;
- no business logic: facts come from the existing engine stores and wire
  mapping (``ipc.mapping``), never recomputed here;
- DTO reuse: Protocol v1 wire models (``ipc.dto``) are the output shape; the
  only new views (``capabilities.views``) fill gaps with no wire counterpart;
- bounded by construction: synchronous in-memory reads over ≤ 10 watchlist
  symbols, no I/O, no locks — a capability call can never stall the market
  tick. TIMEOUT is reserved for host-imposed limits.
"""

from __future__ import annotations

from collections.abc import Callable

from market_sentinel.capabilities.errors import CapabilityError, CapabilityErrorCode
from market_sentinel.capabilities.views import (
    _FEED_SEVERITY,
    EventView,
    FeedHealthReport,
    RecentEventsBuffer,
    SymbolFeedHealth,
)
from market_sentinel.domain.enums import FeedStatus
from market_sentinel.intelligence.contract import IntelligenceResult
from market_sentinel.intelligence.registry import AnnotationRegistry
from market_sentinel.ipc.dto import WireMarketState, WireSignal, WireSymbolState
from market_sentinel.ipc.mapping import map_engine_state, map_signal, map_symbol_state
from market_sentinel.market_data.normalizer import is_valid_symbol
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.runtime.results import EngineTickResult


class MarketCapabilities:
    """Facade over one MarketEngine instance.

    ``started`` lets the tick-loop owner gate reads on its own lifecycle
    (e.g. a daemon phase or a future MCP server start flag). When provided
    and returning False, every capability raises ``NOT_RUNNING``.
    """

    MAX_RECENT_EVENTS = 200

    def __init__(
        self,
        engine: MarketEngine,
        *,
        events: RecentEventsBuffer | None = None,
        started: Callable[[], bool] | None = None,
    ) -> None:
        self._engine = engine
        self._events = events if events is not None else RecentEventsBuffer()
        self._started = started

    def observe_tick(self, result: EngineTickResult) -> None:
        """Publish a finished tick's accepted events to the recent-events buffer.

        Optional host hook: reading it back is :meth:`get_recent_events`.
        Observation only — the engine result is treated as immutable.
        """
        self._events.observe_tick(result)

    def get_market_state(self) -> WireMarketState:
        """Whole-watchlist snapshot, identical to the daemon's ``state`` payload."""
        self._require_started()
        return map_engine_state(self._engine)

    def get_symbol_state(self, symbol: str) -> WireSymbolState:
        """One symbol's snapshot, or NOT_FOUND when it is not on the watchlist."""
        self._require_started()
        self._ensure_known_symbol(symbol)
        return map_symbol_state(
            symbol, self._engine.states.get(symbol), intelligence_of=self._intelligence_of
        )

    def get_active_signals(self) -> dict[str, tuple[WireSignal, ...]]:
        """Signals still inside their episode lifecycle, grouped by symbol.

        WireSignal carries no symbol field (Protocol v1 nests signals under
        symbols), so the grouping is the symbol context. Empty groups are
        omitted.
        """
        self._require_started()
        out: dict[str, tuple[WireSignal, ...]] = {}
        for item in self._engine.watchlist.list():
            state = self._engine.states.get(item.symbol)
            if state is None or not state.active_signals:
                continue
            out[item.symbol] = tuple(
                map_signal(signal, self._intelligence_of(signal.id))
                for signal in state.active_signals
            )
        return out

    def get_signal(self, signal_id: str) -> WireSignal:
        """One active-episode signal with its intelligence annotation, if any.

        Only signals still inside their episode lifecycle are visible; the
        core does not retain expired signals, so there is no history query.
        """
        self._require_started()
        if not isinstance(signal_id, str) or signal_id.strip() == "":
            raise CapabilityError(
                CapabilityErrorCode.INVALID_ARGUMENT, "signal_id must be a non-empty string"
            )
        for item in self._engine.watchlist.list():
            state = self._engine.states.get(item.symbol)
            if state is None:
                continue
            for signal in state.active_signals:
                if signal.id == signal_id:
                    return map_signal(signal, self._intelligence_of(signal_id))
        raise CapabilityError(CapabilityErrorCode.NOT_FOUND, f"signal not found: {signal_id}")

    def get_feed_health(self) -> FeedHealthReport:
        """Per-symbol feed health plus the worst-of aggregate.

        Built on peek_status() so reads never touch the tracker's log-dedup
        bookkeeping field.
        """
        self._require_started()
        rows: list[SymbolFeedHealth] = []
        for item in self._engine.watchlist.list():
            status = self._engine.health.peek_status(item.symbol)
            rows.append(
                SymbolFeedHealth(
                    symbol=item.symbol,
                    status=status.value,
                    feed_latency_s=self._engine.health.feed_latency(item.symbol),
                    last_update_age_s=self._engine.health.last_update_age(item.symbol),
                )
            )
        if rows:
            aggregate = max(
                (row.status for row in rows),
                key=lambda value: _FEED_SEVERITY[FeedStatus(value)],
            )
        else:
            aggregate = FeedStatus.DISCONNECTED.value
        return FeedHealthReport(aggregate_status=aggregate, symbols=tuple(rows))

    def get_recent_events(
        self, *, symbol: str | None = None, limit: int = 20
    ) -> tuple[EventView, ...]:
        """Recently accepted events, chronological (newest last).

        Served from the host-fed RecentEventsBuffer; empty when the host
        never publishes ticks. ``symbol`` filters without changing semantics.
        """
        self._require_started()
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise CapabilityError(
                CapabilityErrorCode.INVALID_ARGUMENT,
                f"limit must be an integer in [1, {self.MAX_RECENT_EVENTS}]",
            )
        if not 1 <= limit <= self.MAX_RECENT_EVENTS:
            raise CapabilityError(
                CapabilityErrorCode.INVALID_ARGUMENT,
                f"limit must be an integer in [1, {self.MAX_RECENT_EVENTS}]",
            )
        if symbol is not None and not is_valid_symbol(symbol):
            raise CapabilityError(
                CapabilityErrorCode.INVALID_ARGUMENT,
                "invalid symbol format; expected e.g. 600519.SH",
            )
        return self._events.recent(symbol=symbol, limit=limit)

    def _require_started(self) -> None:
        if self._started is not None and not self._started():
            raise CapabilityError(CapabilityErrorCode.NOT_RUNNING, "core is not running")

    def _ensure_known_symbol(self, symbol: str) -> None:
        if not isinstance(symbol, str) or not is_valid_symbol(symbol):
            raise CapabilityError(
                CapabilityErrorCode.INVALID_ARGUMENT,
                "invalid symbol format; expected e.g. 600519.SH",
            )
        known = {item.symbol for item in self._engine.watchlist.list()}
        if symbol not in known:
            raise CapabilityError(
                CapabilityErrorCode.NOT_FOUND, f"symbol is not on the watchlist: {symbol}"
            )

    def _intelligence_of(self, signal_id: str) -> IntelligenceResult | None:
        registry = self._registry()
        if registry is None:
            return None
        return registry.get(signal_id)

    def _registry(self) -> AnnotationRegistry | None:
        intelligence = self._engine.intelligence
        return None if intelligence is None else intelligence.registry

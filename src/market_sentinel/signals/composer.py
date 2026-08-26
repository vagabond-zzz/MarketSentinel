from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Sequence

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import EventDirection, GeneratedBy
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.signals.cluster import (
    CLUSTER_LOOKBACK_S,
    classify_family,
    lineage_of,
    partition_lineage_episodes,
)
from market_sentinel.signals.copy import compose_priority, render_copy

_LINEAGE_ORDER = {"tape": 0, "vwap": 1}
_DIRECTION_ORDER = {
    EventDirection.NONE: 0,
    EventDirection.UP: 1,
    EventDirection.DOWN: 2,
}


class SignalComposer:
    """Compose or upgrade Signals immediately from accepted events.

    A Signal ID is one look-back-continuous directional episode, not a
    permanent (symbol, lineage) slot.
    """

    def __init__(self, clock: Clock, lookback_s: float = CLUSTER_LOOKBACK_S) -> None:
        self._clock = clock
        self._lookback_s = lookback_s
        self._accepted: dict[str, list[MarketEvent]] = defaultdict(list)
        self._active: dict[tuple[str, str, EventDirection], Signal] = {}
        self._traces: dict[str, SignalTrace] = {}

    def active_signals(self, symbol: str) -> tuple[Signal, ...]:
        rows = [
            (_LINEAGE_ORDER.get(lineage, 9), _DIRECTION_ORDER.get(direction, 9), signal.id, signal)
            for (sym, lineage, direction), signal in self._active.items()
            if sym == symbol
        ]
        rows.sort()
        return tuple(row[-1] for row in rows)

    def trace_for(self, signal_id: str) -> SignalTrace:
        return self._traces[signal_id]

    def consume(self, event: MarketEvent, features: MarketFeatures) -> tuple[Signal, SignalTrace]:
        produced = self.consume_batch((event,), features)
        for signal, trace in produced:
            if event.id in signal.event_ids:
                return signal, trace
        raise RuntimeError("accepted event was not composed into a signal")

    def consume_batch(
        self,
        events: Sequence[MarketEvent],
        features: MarketFeatures,
    ) -> list[tuple[Signal, SignalTrace]]:
        if not events:
            return []
        produced: list[tuple[Signal, SignalTrace]] = []
        by_symbol: dict[str, list[MarketEvent]] = defaultdict(list)
        for event in events:
            by_symbol[event.symbol].append(event)
        for symbol, batch in by_symbol.items():
            produced.extend(self._consume_symbol(symbol, batch, features))
        return produced

    def _consume_symbol(
        self,
        symbol: str,
        batch: Sequence[MarketEvent],
        features: MarketFeatures,
    ) -> list[tuple[Signal, SignalTrace]]:
        now_ts = max(item.market_timestamp for item in batch)
        history = self._accepted[symbol]
        history.extend(batch)
        cutoff = now_ts - self._lookback_s
        self._accepted[symbol] = [item for item in history if item.market_timestamp >= cutoff]
        recent = self._accepted[symbol]
        self._prune_active(now_ts)
        new_ids = {item.id for item in batch}
        stolen_none: set[tuple[str, str]] = set()
        produced: list[tuple[Signal, SignalTrace]] = []
        for lineage in ("tape", "vwap"):
            if not any(lineage_of(item.type) == lineage for item in batch):
                continue
            lineage_recent = [item for item in recent if lineage_of(item.type) == lineage]
            for direction, members in partition_lineage_episodes(lineage_recent):
                if not any(item.id in new_ids for item in members):
                    continue
                produced.append(
                    self._compose_episode(
                        symbol,
                        lineage,
                        direction,
                        members,
                        features,
                        now_ts,
                        stolen_none,
                    )
                )
        return produced

    def _compose_episode(
        self,
        symbol: str,
        lineage: str,
        direction: EventDirection,
        members: list[MarketEvent],
        features: MarketFeatures,
        now_ts: float,
        stolen_none: set[tuple[str, str]],
    ) -> tuple[Signal, SignalTrace]:
        signal_id, created_at = self._resolve_identity(
            symbol, lineage, direction, now_ts, stolen_none
        )
        family = classify_family(members)
        priority, reason = compose_priority(members, family)
        title, summary = render_copy(members, family, features)
        latest = members[-1]
        signal = Signal(
            id=signal_id,
            event_ids=tuple(item.id for item in members),
            symbol=symbol,
            family=family,
            direction=direction,
            priority=priority,
            title=title,
            summary=summary,
            generated_by=GeneratedBy.RULE,
            market_timestamp=latest.market_timestamp,
            received_timestamp=latest.received_timestamp,
            detected_timestamp=latest.detected_timestamp,
            signal_created_timestamp=created_at,
        )
        self._active[(symbol, lineage, direction)] = signal
        trace = SignalTrace(
            signal_id=signal.id,
            event_ids=signal.event_ids,
            rule_names=tuple(item.rule_name for item in members),
            features=features,
            family=family,
            direction=direction,
            priority=priority,
            priority_reason=reason,
            detected_timestamp=signal.detected_timestamp,
            signal_created_timestamp=created_at,
        )
        self._traces[signal.id] = trace
        return signal, trace

    def _resolve_identity(
        self,
        symbol: str,
        lineage: str,
        direction: EventDirection,
        now_ts: float,
        stolen_none: set[tuple[str, str]],
    ) -> tuple[str, float]:
        cutoff = now_ts - self._lookback_s
        existing = self._active.get((symbol, lineage, direction))
        if existing is not None and existing.market_timestamp >= cutoff:
            return existing.id, existing.signal_created_timestamp
        none_key = (symbol, lineage)
        if direction is not EventDirection.NONE and none_key not in stolen_none:
            none_signal = self._active.get((symbol, lineage, EventDirection.NONE))
            if none_signal is not None and none_signal.market_timestamp >= cutoff:
                self._active.pop((symbol, lineage, EventDirection.NONE), None)
                stolen_none.add(none_key)
                return none_signal.id, none_signal.signal_created_timestamp
        return uuid.uuid4().hex, self._clock.wall_time()

    def _prune_active(self, now_ts: float) -> None:
        cutoff = now_ts - self._lookback_s
        expired = [key for key, signal in self._active.items() if signal.market_timestamp < cutoff]
        for key in expired:
            signal = self._active.pop(key)
            self._traces.pop(signal.id, None)

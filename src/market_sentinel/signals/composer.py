from __future__ import annotations

import uuid
from collections import defaultdict

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import GeneratedBy
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.signals.cluster import (
    CLUSTER_LOOKBACK_S,
    classify_family,
    cluster_members,
    events_in_lookback,
    lineage_of,
)
from market_sentinel.signals.copy import compose_priority, render_copy


class SignalComposer:
    """Compose or upgrade a Signal as soon as an accepted event arrives.

    The 90s window is a look-back over already accepted events, not a delay.
    """

    def __init__(self, clock: Clock, lookback_s: float = CLUSTER_LOOKBACK_S) -> None:
        self._clock = clock
        self._lookback_s = lookback_s
        self._accepted: dict[str, list[MarketEvent]] = defaultdict(list)
        self._active: dict[tuple[str, str], Signal] = {}

    def consume(self, event: MarketEvent, features: MarketFeatures) -> tuple[Signal, SignalTrace]:
        history = self._accepted[event.symbol]
        history.append(event)
        recent = events_in_lookback(
            history,
            now_market_ts=event.market_timestamp,
            lookback_s=self._lookback_s,
        )
        self._accepted[event.symbol] = [
            item
            for item in history
            if item.market_timestamp >= event.market_timestamp - self._lookback_s
        ]
        members = cluster_members(event, recent)
        family = classify_family(members)
        priority, reason = compose_priority(members, family)
        title, summary = render_copy(members, family, features)
        lineage = lineage_of(event.type)
        key = (event.symbol, lineage)
        existing = self._active.get(key)
        if existing is None:
            signal_id = uuid.uuid4().hex
            created_at = self._clock.wall_time()
        else:
            signal_id = existing.id
            created_at = existing.signal_created_timestamp
        latest = members[-1]
        signal = Signal(
            id=signal_id,
            event_ids=tuple(item.id for item in members),
            symbol=event.symbol,
            family=family,
            priority=priority,
            title=title,
            summary=summary,
            generated_by=GeneratedBy.RULE,
            market_timestamp=latest.market_timestamp,
            received_timestamp=latest.received_timestamp,
            detected_timestamp=latest.detected_timestamp,
            signal_created_timestamp=created_at,
        )
        self._active[key] = signal
        trace = SignalTrace(
            signal_id=signal.id,
            event_ids=signal.event_ids,
            rule_names=tuple(item.rule_name for item in members),
            features=features,
            family=family,
            priority=priority,
            priority_reason=reason,
            detected_timestamp=signal.detected_timestamp,
            signal_created_timestamp=created_at,
        )
        return signal, trace

from __future__ import annotations

from collections.abc import Sequence

from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent

CLUSTER_LOOKBACK_S = 90.0

_TAPE_TYPES = frozenset(
    {
        EventType.RAPID_MOVE,
        EventType.VOLUME_SPIKE,
        EventType.PRICE_VOLUME_EXPANSION,
        EventType.DAY_HIGH_BREAKOUT,
        EventType.DAY_LOW_BREAKDOWN,
    }
)


def lineage_of(event_type: EventType) -> str:
    if event_type is EventType.VWAP_CROSS:
        return "vwap"
    return "tape"


def events_in_lookback(
    accepted: Sequence[MarketEvent],
    *,
    now_market_ts: float,
    lookback_s: float = CLUSTER_LOOKBACK_S,
) -> list[MarketEvent]:
    start = now_market_ts - lookback_s
    return [event for event in accepted if start <= event.market_timestamp <= now_market_ts]


def cluster_members(event: MarketEvent, recent: Sequence[MarketEvent]) -> list[MarketEvent]:
    lineage = lineage_of(event.type)
    if lineage == "vwap":
        members = [item for item in recent if item.type is EventType.VWAP_CROSS]
    else:
        members = [item for item in recent if item.type in _TAPE_TYPES]
    return _compatible_members(event, members)


def _compatible_members(event: MarketEvent, members: Sequence[MarketEvent]) -> list[MarketEvent]:
    if event.direction is EventDirection.NONE:
        selected = list(members)
    else:
        selected = [
            item for item in members if item.direction in {event.direction, EventDirection.NONE}
        ]
    selected.sort(key=lambda item: (item.market_timestamp, item.id))
    return selected


def partition_lineage_episodes(
    recent: Sequence[MarketEvent],
    *,
    none_target: EventDirection,
) -> list[tuple[EventDirection, list[MarketEvent]]]:
    """Split one lineage's look-back events into directional episodes.

    NONE events are assigned to exactly one episode, given by ``none_target``.
    """
    ups = [item for item in recent if item.direction is EventDirection.UP]
    downs = [item for item in recent if item.direction is EventDirection.DOWN]
    nones = [item for item in recent if item.direction is EventDirection.NONE]
    none_up = nones if none_target is EventDirection.UP else []
    none_down = nones if none_target is EventDirection.DOWN else []
    none_alone = nones if none_target is EventDirection.NONE else []
    episodes: list[tuple[EventDirection, list[MarketEvent]]] = []
    if ups or none_up:
        episodes.append(
            (
                EventDirection.UP,
                sorted(none_up + ups, key=lambda item: (item.market_timestamp, item.id)),
            )
        )
    if downs or none_down:
        episodes.append(
            (
                EventDirection.DOWN,
                sorted(none_down + downs, key=lambda item: (item.market_timestamp, item.id)),
            )
        )
    if none_alone:
        episodes.append(
            (
                EventDirection.NONE,
                sorted(none_alone, key=lambda item: (item.market_timestamp, item.id)),
            )
        )
    return episodes


def resolve_none_target(
    batch: Sequence[MarketEvent],
    recent: Sequence[MarketEvent],
    live_directions: frozenset[EventDirection],
) -> EventDirection:
    """Deterministic home for NONE events in this batch. Never duplicates them."""
    batch_dirs = {
        item.direction
        for item in batch
        if item.direction in {EventDirection.UP, EventDirection.DOWN}
    }
    if batch_dirs == {EventDirection.UP}:
        return EventDirection.UP
    if batch_dirs == {EventDirection.DOWN}:
        return EventDirection.DOWN
    if len(batch_dirs) > 1:
        return EventDirection.NONE
    lookback_dirs = {
        item.direction
        for item in recent
        if item.direction in {EventDirection.UP, EventDirection.DOWN}
    }
    candidates = lookback_dirs | (live_directions & {EventDirection.UP, EventDirection.DOWN})
    if candidates == {EventDirection.UP}:
        return EventDirection.UP
    if candidates == {EventDirection.DOWN}:
        return EventDirection.DOWN
    return EventDirection.NONE


def classify_family(events: Sequence[MarketEvent]) -> str:
    types = {item.type for item in events}
    has_vol = bool(types & {EventType.VOLUME_SPIKE, EventType.PRICE_VOLUME_EXPANSION})
    has_move = bool(types & {EventType.RAPID_MOVE, EventType.PRICE_VOLUME_EXPANSION})
    if has_vol and has_move:
        return "price_volume"
    if EventType.DAY_HIGH_BREAKOUT in types:
        return "breakout"
    if EventType.DAY_LOW_BREAKDOWN in types:
        return "breakdown"
    if has_vol:
        return "volume"
    if has_move:
        return "move"
    if EventType.VWAP_CROSS in types:
        return "vwap"
    return "other"

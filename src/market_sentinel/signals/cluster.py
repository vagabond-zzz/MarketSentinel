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
) -> list[tuple[EventDirection, list[MarketEvent]]]:
    """Split one lineage's look-back events into directional episodes.

    NONE (e.g. volume_spike) may join UP or DOWN. UP and DOWN never share an episode.
    """
    ups = [item for item in recent if item.direction is EventDirection.UP]
    downs = [item for item in recent if item.direction is EventDirection.DOWN]
    nones = [item for item in recent if item.direction is EventDirection.NONE]
    episodes: list[tuple[EventDirection, list[MarketEvent]]] = []
    if ups:
        episodes.append(
            (
                EventDirection.UP,
                sorted(nones + ups, key=lambda item: (item.market_timestamp, item.id)),
            )
        )
    if downs:
        episodes.append(
            (
                EventDirection.DOWN,
                sorted(nones + downs, key=lambda item: (item.market_timestamp, item.id)),
            )
        )
    if nones and not ups and not downs:
        episodes.append(
            (EventDirection.NONE, sorted(nones, key=lambda item: (item.market_timestamp, item.id)))
        )
    return episodes


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

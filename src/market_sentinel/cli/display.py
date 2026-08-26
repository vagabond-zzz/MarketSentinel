from __future__ import annotations

from datetime import UTC, datetime

from market_sentinel.domain.enums import EventDirection, FeedStatus, SignalPriority
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.models import MarketState
from market_sentinel.domain.signals import Signal
from market_sentinel.runtime.results import EngineTickResult, SymbolTickResult

NA = "N/A"
_SEP = "=" * 60
_SUB = "-" * 60
_LABEL = 12


def format_percent(value: float | None) -> str:
    if value is None:
        return NA
    return f"{value * 100:+.2f}%"


def format_ratio(value: float | None) -> str:
    if value is None:
        return NA
    return f"{value:.2f}x"


def format_price(value: float | None) -> str:
    if value is None:
        return NA
    return f"{value:.2f}"


def format_seconds(value: float | None) -> str:
    if value is None:
        return NA
    return f"{value:.2f}s"


def format_rsi(value: float | None) -> str:
    if value is None:
        return NA
    return f"{value:.1f}"


def format_updated(wall_time: float) -> str:
    return datetime.fromtimestamp(wall_time, tz=UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_direction(direction: EventDirection) -> str:
    return direction.name


def format_priority(priority: SignalPriority) -> str:
    return priority.name


def format_position(above_vwap: bool | None) -> str:
    if above_vwap is None:
        return NA
    return "ABOVE" if above_vwap else "BELOW"


def format_dashboard(
    feed: FeedStatus,
    states: list[MarketState],
    *,
    watchlist_count: int,
    tick_result: EngineTickResult | None = None,
    updated: str | None = None,
    verbose: bool = False,
) -> str:
    lines = [
        "MARKET SENTINEL",
        "",
        f"Feed: {feed.value}",
        f"Watchlist: {watchlist_count}",
    ]
    if updated is not None:
        lines.append(f"Updated: {updated}")
    lines.append("")
    for state in states:
        tick = None if tick_result is None else tick_result.for_symbol(state.symbol)
        lines.extend(render_symbol_state(state, tick, verbose=verbose))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_symbol_state(
    state: MarketState,
    tick: SymbolTickResult | None,
    *,
    verbose: bool = False,
) -> list[str]:
    lines = [
        _SEP,
        f"{state.symbol}  {state.level.value}",
        _SUB,
    ]
    lines.extend(render_persistent_state(state, tick, verbose=verbose))
    lines.append("")
    lines.extend(render_active_signals(state.active_signals, verbose=verbose))
    lines.append("")
    events = () if tick is None else tick.accepted_events
    alerts = () if tick is None else tick.alert_candidates
    lines.extend(render_events_this_tick(events, verbose=verbose))
    lines.append("")
    lines.extend(render_alerts_this_tick(alerts, verbose=verbose))
    lines.append(_SEP)
    return lines


def render_persistent_state(
    state: MarketState,
    tick: SymbolTickResult | None,
    *,
    verbose: bool = False,
) -> list[str]:
    latest = state.latest
    features = state.features
    price = NA if latest is None else format_price(latest.price)
    lines = [
        _field("Price", price),
        _field("1m", format_percent(_feature(features, "change_1m"))),
        _field("5m", format_percent(_feature(features, "change_5m"))),
        _field("15m", format_percent(_feature(features, "change_15m"))),
        "",
        _field("Volume 1m", format_ratio(_feature(features, "volume_ratio_1m"))),
        _field("Volume 5m", format_ratio(_feature(features, "volume_ratio_5m"))),
        "",
        _field("VWAP", format_price(_feature(features, "vwap"))),
        _field("Position", format_position(None if features is None else features.above_vwap)),
        _field("EMA5", format_price(_feature(features, "ema5"))),
        _field("EMA20", format_price(_feature(features, "ema20"))),
        _field("RSI14", format_rsi(_feature(features, "rsi14"))),
        "",
        _field("Feed", state.feed_status.value),
        _field("Latency", format_seconds(state.feed_latency)),
        _field("Age", format_seconds(state.last_update_age)),
    ]
    if verbose:
        lines.extend(_verbose_persistent(state, tick))
    return lines


def render_active_signals(signals: tuple[Signal, ...], *, verbose: bool = False) -> list[str]:
    lines = ["ACTIVE SIGNALS"]
    if not signals:
        lines.append("None")
        return lines
    for index, signal in enumerate(signals):
        if index:
            lines.append("")
        lines.append(
            f"[{format_priority(signal.priority)}] [{format_direction(signal.direction)}] "
            f"{signal.family}"
        )
        lines.append(signal.title)
        lines.append(signal.summary)
        lines.append(f"Events: {len(signal.event_ids)}")
        if verbose:
            lines.append(f"id {signal.id}")
    return lines


def render_events_this_tick(
    events: tuple[MarketEvent, ...],
    *,
    verbose: bool = False,
) -> list[str]:
    lines = ["EVENTS THIS TICK"]
    if not events:
        lines.append("None")
        return lines
    for event in events:
        row = f"[{event.severity}] {event.type.value} {format_direction(event.direction)}"
        if verbose:
            row = f"{row} id={event.id}"
        lines.append(row)
    return lines


def render_alerts_this_tick(
    alerts: tuple[Signal, ...],
    *,
    verbose: bool = False,
) -> list[str]:
    lines = ["ALERTS THIS TICK"]
    if not alerts:
        lines.append("None")
        return lines
    for signal in alerts:
        row = f"[{format_priority(signal.priority)}] {signal.title}"
        if verbose:
            row = f"{row} id={signal.id}"
        lines.append(row)
    return lines


def _field(label: str, value: str) -> str:
    return f"{label:<{_LABEL}} {value}"


def _feature(features: MarketFeatures | None, name: str) -> float | None:
    if features is None:
        return None
    value = getattr(features, name)
    return value if isinstance(value, float) else None


def _verbose_persistent(state: MarketState, tick: SymbolTickResult | None) -> list[str]:
    lines = [""]
    if tick is None:
        lines.append(f"Scheduler: {state.level.value}")
    else:
        lines.append(f"Scheduler: {tick.level_before.value} -> {tick.level_after.value}")
    source = state.features if state.features is not None else state.latest
    if source is None:
        lines.append(f"market_timestamp {NA}")
        lines.append(f"received_timestamp {NA}")
    else:
        lines.append(f"market_timestamp {source.market_timestamp:.3f}")
        lines.append(f"received_timestamp {source.received_timestamp:.3f}")
    return lines

from __future__ import annotations

from market_sentinel.domain.enums import FeedStatus
from market_sentinel.domain.models import MarketState


def format_dashboard(
    feed: FeedStatus,
    states: list[MarketState],
    *,
    watchlist_count: int,
) -> str:
    lines = [
        "MARKET SENTINEL",
        "",
        f"Feed: {feed.value}",
        f"Watchlist: {watchlist_count}",
        "",
    ]
    for state in states:
        lines.append(_format_row(state))
    return "\n".join(lines)


def _format_row(state: MarketState) -> str:
    latest = state.latest
    if latest is None:
        price = "   n/a"
        change = "     n/a"
    else:
        price = f"{latest.price:.2f}"
        change = _percent_change(latest.price, latest.prev_close)
    age = "n/a" if state.last_update_age is None else f"{state.last_update_age:.1f}s"
    lat = "n/a" if state.feed_latency is None else f"{state.feed_latency:.1f}s"
    return (
        f"{state.symbol:<10} {price:>8} {change:>8}  {state.level.value:<4}  age={age}  lat={lat}"
    )


def _percent_change(price: float, prev_close: float) -> str:
    if prev_close == 0:
        return "n/a"
    change = (price - prev_close) / prev_close * 100
    return f"{change:+.2f}%"

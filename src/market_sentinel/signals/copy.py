from __future__ import annotations

from collections.abc import Sequence

from market_sentinel.domain.enums import EventType, SignalPriority
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures

_PRIORITY_RANK = {
    SignalPriority.INFO: 1,
    SignalPriority.NOTICE: 2,
    SignalPriority.IMPORTANT: 3,
    SignalPriority.CRITICAL: 4,
}


def max_priority(*priorities: SignalPriority) -> SignalPriority:
    return max(priorities, key=lambda item: _PRIORITY_RANK[item])


def priority_from_severity(severity: int) -> SignalPriority:
    if severity >= 5:
        return SignalPriority.CRITICAL
    if severity >= 4:
        return SignalPriority.IMPORTANT
    if severity >= 3:
        return SignalPriority.NOTICE
    return SignalPriority.INFO


def compose_priority(events: Sequence[MarketEvent], family: str) -> tuple[SignalPriority, str]:
    max_severity = max(item.severity for item in events)
    base = priority_from_severity(max_severity)
    types = {item.type for item in events}
    has_vol = bool(types & {EventType.VOLUME_SPIKE, EventType.PRICE_VOLUME_EXPANSION})
    has_move = bool(types & {EventType.RAPID_MOVE, EventType.PRICE_VOLUME_EXPANSION})
    if family == "price_volume" or (has_vol and has_move):
        chosen = max_priority(base, SignalPriority.IMPORTANT)
        reason = f"family={family}; max_severity={max_severity}; cluster=price_volume"
        return chosen, reason
    if family == "volume":
        chosen = max_priority(base, SignalPriority.NOTICE)
        reason = f"family=volume; max_severity={max_severity}; standalone_volume_notice"
        return chosen, reason
    reason = f"family={family}; max_severity={max_severity}"
    return base, reason


def render_copy(
    events: Sequence[MarketEvent], family: str, features: MarketFeatures
) -> tuple[str, str]:
    symbol = events[-1].symbol
    titles = {
        "volume": f"{symbol} 成交量明显放大",
        "move": f"{symbol} 出现短时快速涨跌",
        "price_volume": f"{symbol} 出现量价同步扩张",
        "breakout": f"{symbol} 突破日内高点",
        "breakdown": f"{symbol} 跌破日内低点",
        "vwap": f"{symbol} 价格穿越VWAP",
        "other": f"{symbol} 出现市场异动",
    }
    facts: list[str] = []
    if features.change_1m is not None:
        facts.append(f"1分钟涨跌 {features.change_1m * 100:+.2f}%")
    if features.change_5m is not None:
        facts.append(f"5分钟涨跌 {features.change_5m * 100:+.2f}%")
    if features.volume_ratio_1m is not None:
        facts.append(f"1分钟成交量 {features.volume_ratio_1m:.2f} 倍")
    if features.volume_ratio_5m is not None:
        facts.append(f"5分钟成交量 {features.volume_ratio_5m:.2f} 倍")
    if features.session_high_ref is not None:
        facts.append(
            f"观测日内高 {features.session_high_obs:.2f} vs 前高 {features.session_high_ref:.2f}"
        )
    if features.session_low_ref is not None:
        facts.append(
            f"观测日内低 {features.session_low_obs:.2f} vs 前低 {features.session_low_ref:.2f}"
        )
    if features.vwap is not None and features.above_vwap is not None:
        side = "上方" if features.above_vwap else "下方"
        facts.append(f"价格位于VWAP{side} {features.vwap:.2f}")
    types = " + ".join(sorted({item.type.value for item in events}))
    facts.append(f"触发规则 {types}")
    return titles.get(family, titles["other"]), "，".join(facts)

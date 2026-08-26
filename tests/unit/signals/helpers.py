from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent


def make_event(
    *,
    symbol: str = "00700.HK",
    event_type: EventType = EventType.RAPID_MOVE,
    direction: EventDirection = EventDirection.UP,
    severity: int = 2,
    market_timestamp: float = 1_700_000_000.0,
    ttl_s: float = 60.0,
) -> MarketEvent:
    return MarketEvent(
        id=f"{symbol}:{event_type}:{market_timestamp}:{severity}",
        symbol=symbol,
        type=event_type,
        direction=direction,
        severity=severity,
        market_timestamp=market_timestamp,
        received_timestamp=market_timestamp + 1.0,
        detected_timestamp=market_timestamp + 2.0,
        metrics={},
        dedupe_key=f"{symbol}|{event_type.value}|{direction.value}",
        ttl_s=ttl_s,
        rule_name=event_type.value,
    )

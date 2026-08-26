from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.domain.events import MarketEvent
from tests.unit.events.helpers import DETECTED_AT, make_features


def test_market_event_model_fields() -> None:
    features = make_features(change_1m=0.006)
    event = MarketEvent(
        id="abc",
        symbol=features.symbol,
        type=EventType.RAPID_MOVE,
        direction=EventDirection.UP,
        severity=2,
        market_timestamp=features.market_timestamp,
        received_timestamp=features.received_timestamp,
        detected_timestamp=DETECTED_AT,
        metrics={"change_1m": 0.006},
        dedupe_key="00700.HK|rapid_move|up",
        ttl_s=60.0,
        rule_name="rapid_move",
    )
    assert event.severity == 2
    assert "notified" not in event.__dataclass_fields__

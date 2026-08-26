from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventType, GeneratedBy, SignalPriority
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.copy import render_copy
from tests.unit.events.helpers import make_features
from tests.unit.signals.helpers import make_event

_FORBIDDEN = ("BUY", "SELL", "买入", "卖出", "建议", "做多", "做空")


def test_signal_copy_is_factual_and_has_no_trade_advice() -> None:
    event = make_event(event_type=EventType.VOLUME_SPIKE, ttl_s=120.0)
    features = make_features(volume_ratio_5m=1.8, change_1m=0.006)
    title, summary = render_copy([event], "volume", features)
    blob = f"{title} {summary}"
    for word in _FORBIDDEN:
        assert word not in blob
    assert "1.80 倍" in summary
    assert "买入" not in blob


def test_signal_and_trace_record_v02_timestamps_only() -> None:
    clock = FakeClock(wall=5_000.0)
    composer = SignalComposer(clock)
    event = make_event(event_type=EventType.VOLUME_SPIKE, market_timestamp=200.0, ttl_s=120.0)
    signal, trace = composer.consume(
        event, make_features(volume_ratio_5m=2.0, market_timestamp=200.0)
    )
    assert signal.market_timestamp == 200.0
    assert signal.received_timestamp == 201.0
    assert signal.detected_timestamp == 202.0
    assert signal.signal_created_timestamp == 5_000.0
    assert signal.generated_by is GeneratedBy.RULE
    assert trace.signal_created_timestamp == 5_000.0
    assert set(Signal.__dataclass_fields__) >= {
        "market_timestamp",
        "received_timestamp",
        "detected_timestamp",
        "signal_created_timestamp",
    }
    assert "notified_timestamp" not in Signal.__dataclass_fields__
    assert "notified_timestamp" not in SignalTrace.__dataclass_fields__


def test_standalone_rapid_move_is_not_delayed() -> None:
    composer = SignalComposer(FakeClock(wall=1.0))
    event = make_event(event_type=EventType.RAPID_MOVE, market_timestamp=50.0)
    signal, _ = composer.consume(event, make_features(change_1m=0.006))
    assert signal.family == "move"
    assert signal.priority is SignalPriority.INFO

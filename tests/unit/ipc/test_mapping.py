from tests.unit.ipc.helpers import make_engine

from market_sentinel.domain.enums import (
    EventDirection,
    FeedStatus,
    GeneratedBy,
    SchedulerLevel,
    SignalPriority,
)
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.models import MarketSnapshot, MarketState
from market_sentinel.domain.signals import Signal
from market_sentinel.ipc.mapping import map_engine_state, map_symbol_state
from market_sentinel.watchlist.watchlist import Watchlist


def _features() -> MarketFeatures:
    return MarketFeatures(
        symbol="00700.HK",
        market_timestamp=1.0,
        received_timestamp=1.0,
        change_1m=0.006,
        change_5m=None,
        change_15m=None,
        change_day=0.0126,
        day_range_position=None,
        volume_1m=None,
        volume_5m=None,
        volume_ratio_1m=None,
        volume_ratio_5m=1.8,
        vwap=100.0,
        above_vwap=True,
        ema5=100.0,
        ema20=99.0,
        rsi14=55.0,
        session_high_ref=None,
        session_low_ref=None,
        session_high_obs=101.0,
        session_low_obs=99.0,
    )


def test_map_symbol_state_uses_null_not_zero_for_missing_features() -> None:
    wire = map_symbol_state("00700.HK", None)
    assert wire.price is None
    assert wire.change_1m is None
    assert wire.volume_ratio_5m is None
    payload = wire.to_wire()
    assert payload["price"] is None
    assert "feed_latency" not in payload
    assert "traces" not in payload
    assert "metrics" not in payload


def test_map_symbol_state_copies_selected_fields_only() -> None:
    snapshot = MarketSnapshot(
        symbol="00700.HK",
        price=602.5,
        open=595.0,
        high=605.0,
        low=594.0,
        prev_close=595.0,
        volume=1.0,
        turnover=None,
        market_timestamp=1.0,
        received_timestamp=1.0,
    )
    signal = Signal(
        id="sig-1",
        event_ids=("e1",),
        symbol="00700.HK",
        family="tape",
        direction=EventDirection.UP,
        priority=SignalPriority.IMPORTANT,
        title="headline",
        summary="summary",
        generated_by=GeneratedBy.RULE,
        market_timestamp=1.0,
        received_timestamp=1.0,
        detected_timestamp=1.0,
        signal_created_timestamp=1.0,
    )
    state = MarketState(
        symbol="00700.HK",
        latest=snapshot,
        level=SchedulerLevel.HOT,
        feed_status=FeedStatus.LIVE,
        feed_latency=0.2,
        last_update_age=0.8,
        features=_features(),
        active_signals=(signal,),
    )
    payload = map_symbol_state("00700.HK", state).to_wire()
    assert payload["price"] == 602.5
    assert payload["change_1m"] == 0.006
    assert payload["change_5m"] is None
    assert payload["volume_ratio_5m"] == 1.8
    assert payload["change_day"] == 0.0126
    assert payload["above_vwap"] is True
    assert payload["session_high_obs"] == 101.0
    assert payload["market_timestamp"] == 1.0
    assert payload["active_signals"][0]["id"] == "sig-1"
    assert payload["active_signals"][0]["title"] == "headline"
    assert "event_ids" not in payload["active_signals"][0]
    assert "intelligence" not in payload["active_signals"][0]
    assert "feed_latency" not in payload


def test_map_engine_state_empty_watchlist() -> None:
    _, _, engine = make_engine()
    wire = map_engine_state(engine).to_wire()
    assert wire["watchlist_count"] == 0
    assert wire["symbols"] == []
    assert wire["feed_status"] == "DISCONNECTED"


def test_runtime_watchlist_is_used_by_mapper() -> None:
    from market_sentinel.domain.models import WatchItem

    _, _, engine = make_engine()
    engine.watchlist.replace([WatchItem("00700.HK", True)])
    assert isinstance(engine.watchlist, Watchlist)
    wire = map_engine_state(engine).to_wire()
    assert wire["watchlist_count"] == 1
    assert wire["symbols"][0]["symbol"] == "00700.HK"
    assert wire["symbols"][0]["price"] is None


def test_map_signal_adds_optional_intelligence_without_replacing_summary() -> None:
    from market_sentinel.intelligence.contract import (
        FallbackReason,
        IntelligenceAnnotation,
        IntelligenceResult,
        IntelligenceStatus,
    )
    from market_sentinel.ipc.mapping import map_signal

    signal = Signal(
        id="sig-1",
        event_ids=("e1",),
        symbol="00700.HK",
        family="tape",
        direction=EventDirection.UP,
        priority=SignalPriority.IMPORTANT,
        title="headline",
        summary="rule summary",
        generated_by=GeneratedBy.RULE,
        market_timestamp=1.0,
        received_timestamp=1.0,
        detected_timestamp=1.0,
        signal_created_timestamp=1.0,
    )
    omitted = map_signal(signal).to_wire()
    assert omitted["summary"] == "rule summary"
    assert "intelligence" not in omitted
    result = IntelligenceResult(
        signal_id=signal.id,
        status=IntelligenceStatus.ENRICHED,
        requested=True,
        annotation=IntelligenceAnnotation(
            signal_id=signal.id,
            worth_highlight=True,
            reason="cluster",
            confidence=0.8,
            summary="enriched note",
            created_timestamp=2.0,
        ),
        fallback_reason=FallbackReason.NONE,
        model_calls=1,
    )
    payload = map_signal(signal, result).to_wire()
    assert payload["summary"] == "rule summary"
    assert payload["intelligence"]["status"] == "enriched"
    assert payload["intelligence"]["summary"] == "enriched note"

from market_sentinel.cli.display import (
    format_dashboard,
    format_percent,
    format_ratio,
    format_updated,
    render_alerts_this_tick,
    render_events_this_tick,
)
from market_sentinel.domain.enums import (
    EventDirection,
    EventType,
    FeedStatus,
    GeneratedBy,
    SchedulerLevel,
    SignalPriority,
)
from market_sentinel.domain.models import MarketSnapshot, MarketState
from market_sentinel.domain.signals import Signal
from market_sentinel.runtime.results import EngineTickResult, SymbolTickResult
from tests.unit.events.helpers import make_features
from tests.unit.signals.helpers import make_event


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        symbol="00700.HK",
        price=602.5,
        open=595.0,
        high=605.0,
        low=594.0,
        prev_close=595.0,
        volume=1.0,
        turnover=None,
        market_timestamp=1_700_000_010.0,
        received_timestamp=1_700_000_010.2,
    )


def _signal(
    *,
    signal_id: str = "sig-up",
    direction: EventDirection = EventDirection.UP,
    family: str = "price_volume",
    priority: SignalPriority = SignalPriority.IMPORTANT,
    title: str = "00700.HK 出现量价同步扩张",
    summary: str = "1分钟涨跌 +0.80%",
    event_ids: tuple[str, ...] = ("e1", "e2", "e3"),
) -> Signal:
    return Signal(
        id=signal_id,
        event_ids=event_ids,
        symbol="00700.HK",
        family=family,
        direction=direction,
        priority=priority,
        title=title,
        summary=summary,
        generated_by=GeneratedBy.RULE,
        market_timestamp=1_700_000_010.0,
        received_timestamp=1_700_000_010.2,
        detected_timestamp=1_700_000_010.3,
        signal_created_timestamp=1_700_000_010.3,
    )


def _state(
    *,
    level: SchedulerLevel = SchedulerLevel.COLD,
    feed: FeedStatus = FeedStatus.LIVE,
    features=None,
    signals: tuple[Signal, ...] = (),
    latency: float | None = 0.22,
    age: float | None = 0.8,
) -> MarketState:
    return MarketState(
        symbol="00700.HK",
        latest=_snapshot(),
        level=level,
        feed_status=feed,
        feed_latency=latency,
        last_update_age=age,
        features=features,
        active_signals=signals,
    )


def _tick(
    *,
    events=(),
    alerts=(),
    level_before: SchedulerLevel = SchedulerLevel.COLD,
    level_after: SchedulerLevel = SchedulerLevel.HOT,
) -> EngineTickResult:
    return EngineTickResult(
        symbol_results=(
            SymbolTickResult(
                symbol="00700.HK",
                features=None,
                accepted_events=tuple(events),
                signal_updates=(),
                traces=(),
                alert_candidates=tuple(alerts),
                level_before=level_before,
                level_after=level_after,
            ),
        )
    )


def test_missing_features_render_as_na() -> None:
    text = format_dashboard(FeedStatus.LIVE, [_state()], watchlist_count=1)
    assert "1m           N/A" in text
    assert "5m           N/A" in text
    assert "15m          N/A" in text
    assert "Volume 1m    N/A" in text
    assert "Volume 5m    N/A" in text
    assert "VWAP         N/A" in text
    assert "Position     N/A" in text
    assert "EMA20        N/A" in text
    assert "RSI14        N/A" in text
    assert "0.00%" not in text
    assert "1.00x" not in text


def test_percent_and_ratio_formatting() -> None:
    assert format_percent(None) == "N/A"
    assert format_percent(0.006) == "+0.60%"
    assert format_percent(-0.0125) == "-1.25%"
    assert format_ratio(None) == "N/A"
    assert format_ratio(1.8) == "1.80x"
    assert format_ratio(2.63) == "2.63x"


def test_active_signal_is_not_an_alert_this_tick() -> None:
    signal = _signal()
    text = format_dashboard(
        FeedStatus.LIVE,
        [_state(level=SchedulerLevel.HOT, signals=(signal,))],
        watchlist_count=1,
        tick_result=_tick(alerts=()),
    )
    active = text.split("ACTIVE SIGNALS", 1)[1].split("EVENTS THIS TICK", 1)[0]
    alerts = text.split("ALERTS THIS TICK", 1)[1]
    assert "[IMPORTANT] [UP] price_volume" in active
    assert "00700.HK 出现量价同步扩张" in active
    assert "Events: 3" in active
    assert "None" in alerts
    assert "[IMPORTANT] 00700.HK 出现量价同步扩张" not in alerts


def test_edge_alert_disappears_on_second_render() -> None:
    signal = _signal()
    first = format_dashboard(
        FeedStatus.LIVE,
        [_state(level=SchedulerLevel.HOT, signals=(signal,))],
        watchlist_count=1,
        tick_result=_tick(alerts=(signal,)),
    )
    second = format_dashboard(
        FeedStatus.LIVE,
        [_state(level=SchedulerLevel.HOT, signals=(signal,))],
        watchlist_count=1,
        tick_result=_tick(alerts=()),
    )
    first_alerts = first.split("ALERTS THIS TICK", 1)[1]
    second_alerts = second.split("ALERTS THIS TICK", 1)[1]
    assert "[IMPORTANT] 00700.HK 出现量价同步扩张" in first_alerts
    assert "None" not in first_alerts.split("=======", 1)[0]
    assert "None" in second_alerts
    assert "[IMPORTANT] 00700.HK 出现量价同步扩张" not in second_alerts
    assert "ACTIVE SIGNALS" in second
    assert "price_volume" in second.split("ACTIVE SIGNALS", 1)[1]


def test_multiple_active_signals_are_all_shown() -> None:
    signals = (
        _signal(signal_id="up", direction=EventDirection.UP, family="price_volume"),
        _signal(
            signal_id="down",
            direction=EventDirection.DOWN,
            family="move",
            title="00700.HK 出现短时快速涨跌",
        ),
        _signal(
            signal_id="vwap",
            direction=EventDirection.UP,
            family="vwap",
            title="00700.HK 价格穿越VWAP",
            priority=SignalPriority.NOTICE,
        ),
    )
    text = format_dashboard(
        FeedStatus.LIVE,
        [_state(signals=signals)],
        watchlist_count=1,
        tick_result=_tick(alerts=()),
    )
    active = text.split("ACTIVE SIGNALS", 1)[1].split("EVENTS THIS TICK", 1)[0]
    assert "[UP] price_volume" in active
    assert "[DOWN] move" in active
    assert "[UP] vwap" in active
    assert "ALERTS THIS TICK" in text
    assert "None" in text.split("ALERTS THIS TICK", 1)[1]
    assert "BUY" not in text
    assert "SELL" not in text


def test_events_this_tick_are_edge_triggered() -> None:
    event = make_event(
        event_type=EventType.RAPID_MOVE,
        direction=EventDirection.UP,
        severity=3,
    )
    first = "\n".join(render_events_this_tick((event,)))
    second = "\n".join(render_events_this_tick(()))
    assert "[3] rapid_move UP" in first
    assert "EVENTS THIS TICK\nNone" == second


def test_feed_statuses_are_printed_verbatim() -> None:
    for status in FeedStatus:
        text = format_dashboard(status, [_state(feed=status)], watchlist_count=1)
        assert f"Feed: {status.value}" in text
        assert f"Feed         {status.value}" in text


def test_cold_warm_hot_and_feature_values() -> None:
    cold = format_dashboard(FeedStatus.LIVE, [_state(level=SchedulerLevel.COLD)], watchlist_count=1)
    assert "00700.HK  COLD" in cold
    assert "ACTIVE SIGNALS\nNone" in cold
    assert "EVENTS THIS TICK\nNone" in cold
    assert "ALERTS THIS TICK\nNone" in cold

    warm_features = make_features(change_1m=0.004, change_5m=None, volume_ratio_5m=None)
    warm = format_dashboard(
        FeedStatus.LIVE,
        [_state(level=SchedulerLevel.WARM, features=warm_features)],
        watchlist_count=1,
    )
    assert "00700.HK  WARM" in warm
    assert "1m           +0.40%" in warm
    assert "5m           N/A" in warm
    assert "Volume 5m    N/A" in warm

    hot_features = make_features(
        change_1m=0.008,
        change_5m=0.0126,
        volume_ratio_1m=1.42,
        volume_ratio_5m=2.63,
        vwap=598.3,
        above_vwap=True,
        ema5=600.2,
        rsi14=67.4,
    )
    signal = _signal()
    event = make_event(severity=3)
    hot = format_dashboard(
        FeedStatus.LIVE,
        [_state(level=SchedulerLevel.HOT, features=hot_features, signals=(signal,))],
        watchlist_count=1,
        tick_result=_tick(events=(event,), alerts=(signal,)),
        verbose=True,
    )
    assert "00700.HK  HOT" in hot
    assert "1m           +0.80%" in hot
    assert "5m           +1.26%" in hot
    assert "Volume 1m    1.42x" in hot
    assert "Volume 5m    2.63x" in hot
    assert "VWAP         598.30" in hot
    assert "Position     ABOVE" in hot
    assert "RSI14        67.4" in hot
    assert "ALERTS THIS TICK" in hot
    assert "[IMPORTANT] 00700.HK 出现量价同步扩张" in hot.split("ALERTS THIS TICK", 1)[1]
    assert "Scheduler: COLD -> HOT" in hot
    assert "id sig-up" in hot
    assert "\x1b[" not in hot


def test_display_does_not_recompute_scheduler_level() -> None:
    features = make_features(change_5m=0.02)
    text = format_dashboard(
        FeedStatus.LIVE,
        [_state(level=SchedulerLevel.COLD, features=features)],
        watchlist_count=1,
    )
    assert "00700.HK  COLD" in text
    assert "HOT" not in text


def test_empty_alerts_helper() -> None:
    assert "\n".join(render_alerts_this_tick(())) == "ALERTS THIS TICK\nNone"


def test_format_updated_is_utc() -> None:
    assert format_updated(1_700_000_000.0) == "2023-11-14 22:13:20 UTC"


def test_stale_and_disconnected_symbol_rows() -> None:
    stale = format_dashboard(
        FeedStatus.STALE,
        [_state(feed=FeedStatus.STALE, latency=None, age=45.0)],
        watchlist_count=1,
    )
    disconnected = format_dashboard(
        FeedStatus.DISCONNECTED,
        [_state(feed=FeedStatus.DISCONNECTED, latency=None, age=None)],
        watchlist_count=1,
    )
    assert "Feed: STALE" in stale
    assert "Feed         STALE" in stale
    assert "Latency      N/A" in stale
    assert "Age          45.00s" in stale
    assert "Feed: DISCONNECTED" in disconnected
    assert "Feed         DISCONNECTED" in disconnected
    assert "Age          N/A" in disconnected

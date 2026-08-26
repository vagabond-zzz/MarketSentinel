from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.models import MarketSnapshot, MarketState, WatchItem


def test_scheduler_level_members() -> None:
    assert {level.value for level in SchedulerLevel} == {"COLD", "WARM", "HOT"}


def test_feed_status_members() -> None:
    assert {status.value for status in FeedStatus} == {
        "LIVE",
        "DELAYED",
        "STALE",
        "DISCONNECTED",
    }


def test_market_snapshot_stores_wall_timestamps() -> None:
    snapshot = MarketSnapshot(
        symbol="00700.HK",
        price=602.5,
        open=595.0,
        high=605.0,
        low=594.0,
        prev_close=595.0,
        volume=1_000_000.0,
        turnover=602_500_000.0,
        market_timestamp=1_700_000_010.0,
        received_timestamp=1_700_000_011.0,
    )
    assert snapshot.symbol == "00700.HK"
    assert snapshot.market_timestamp == 1_700_000_010.0
    assert snapshot.received_timestamp == 1_700_000_011.0


def test_watch_item_defaults_to_enabled() -> None:
    item = WatchItem(symbol="600519.SH")
    assert item.enabled is True


def test_market_state_holds_latest_snapshot_and_health() -> None:
    snapshot = MarketSnapshot(
        symbol="600519.SH",
        price=1482.3,
        open=1476.0,
        high=1485.0,
        low=1475.0,
        prev_close=1476.0,
        volume=50_000.0,
        turnover=None,
        market_timestamp=1_700_000_000.0,
        received_timestamp=1_700_000_001.0,
    )
    state = MarketState(
        symbol="600519.SH",
        latest=snapshot,
        level=SchedulerLevel.COLD,
        feed_status=FeedStatus.LIVE,
        feed_latency=1.0,
        last_update_age=0.5,
    )
    assert state.latest is snapshot
    assert state.level is SchedulerLevel.COLD
    assert state.feed_status is FeedStatus.LIVE

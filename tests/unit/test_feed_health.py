import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import FeedStatus
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.health.feed_health import FeedHealthTracker, HealthPolicy


def _snapshot(*, market: float, received: float, symbol: str = "00700.HK") -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol,
        price=600.0,
        open=595.0,
        high=605.0,
        low=594.0,
        prev_close=595.0,
        volume=1.0,
        turnover=None,
        market_timestamp=market,
        received_timestamp=received,
    )


def _tracker(clock: FakeClock | None = None) -> tuple[FakeClock, FeedHealthTracker]:
    clock = clock or FakeClock(wall=1_700_000_010.0, monotonic=0.0)
    policy = HealthPolicy(
        delayed_s=3.0,
        stale_s=30.0,
        disconnect_s=60.0,
        disconnect_failures=3,
    )
    return clock, FeedHealthTracker(clock, policy)


def test_fresh_snapshot_is_live() -> None:
    clock, tracker = _tracker()
    status = tracker.observe(
        "00700.HK",
        _snapshot(market=clock.wall_time() - 0.2, received=clock.wall_time()),
    )
    assert status is FeedStatus.LIVE
    assert tracker.feed_latency("00700.HK") == pytest.approx(0.2)
    assert tracker.last_update_age("00700.HK") == 0.0


def test_high_feed_latency_is_delayed() -> None:
    clock, tracker = _tracker()
    status = tracker.observe(
        "00700.HK",
        _snapshot(market=clock.wall_time() - 5.0, received=clock.wall_time()),
    )
    assert status is FeedStatus.DELAYED
    assert tracker.feed_latency("00700.HK") == 5.0


def test_age_without_updates_becomes_stale() -> None:
    clock, tracker = _tracker()
    tracker.observe("00700.HK", _snapshot(market=clock.wall_time(), received=clock.wall_time()))
    clock.advance_monotonic(30.0)
    assert tracker.status("00700.HK") is FeedStatus.STALE


def test_single_timeout_is_not_disconnected() -> None:
    clock, tracker = _tracker()
    tracker.observe("00700.HK", _snapshot(market=clock.wall_time(), received=clock.wall_time()))
    status = tracker.observe("00700.HK", error=TimeoutError("provider timeout"))
    assert status is FeedStatus.LIVE
    assert tracker.status("00700.HK") is not FeedStatus.DISCONNECTED


def test_consecutive_failures_become_disconnected() -> None:
    clock, tracker = _tracker()
    tracker.observe("00700.HK", _snapshot(market=clock.wall_time(), received=clock.wall_time()))
    tracker.observe("00700.HK", error=TimeoutError())
    tracker.observe("00700.HK", error=TimeoutError())
    status = tracker.observe("00700.HK", error=TimeoutError())
    assert status is FeedStatus.DISCONNECTED


def test_disconnect_timeout_uses_monotonic_age() -> None:
    clock, tracker = _tracker()
    tracker.observe("00700.HK", _snapshot(market=clock.wall_time(), received=clock.wall_time()))
    clock.advance_monotonic(60.0)
    assert tracker.status("00700.HK") is FeedStatus.DISCONNECTED


def test_success_recovers_from_disconnected() -> None:
    clock, tracker = _tracker()
    tracker.observe("00700.HK", _snapshot(market=clock.wall_time(), received=clock.wall_time()))
    clock.advance_monotonic(60.0)
    assert tracker.status("00700.HK") is FeedStatus.DISCONNECTED
    status = tracker.observe(
        "00700.HK",
        _snapshot(market=clock.wall_time() - 0.1, received=clock.wall_time()),
    )
    assert status is FeedStatus.LIVE


def test_wall_clock_skew_does_not_go_negative() -> None:
    clock, tracker = _tracker()
    status = tracker.observe(
        "00700.HK",
        _snapshot(market=clock.wall_time() + 2.0, received=clock.wall_time()),
    )
    assert status is FeedStatus.LIVE
    assert tracker.feed_latency("00700.HK") == 0.0

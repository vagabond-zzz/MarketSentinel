import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import SchedulerLevel
from market_sentinel.errors import InvalidSchedulerLevelError
from market_sentinel.scheduler.policy import SchedulerPolicy
from market_sentinel.scheduler.scheduler import AdaptiveScheduler


def _scheduler(clock: FakeClock | None = None) -> tuple[FakeClock, AdaptiveScheduler]:
    clock = clock or FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    return clock, AdaptiveScheduler(clock, SchedulerPolicy())


def test_upgrades_including_cold_to_hot_are_immediate() -> None:
    _, scheduler = _scheduler()
    assert scheduler.set_level("00700.HK", SchedulerLevel.WARM) is True
    assert scheduler.get_level("00700.HK") is SchedulerLevel.WARM
    assert scheduler.set_level("00700.HK", SchedulerLevel.HOT) is True
    assert scheduler.get_level("00700.HK") is SchedulerLevel.HOT
    assert scheduler.set_level("600519.SH", SchedulerLevel.HOT) is True
    assert scheduler.get_level("600519.SH") is SchedulerLevel.HOT


def test_hot_downgrade_requires_dwell() -> None:
    clock, scheduler = _scheduler()
    scheduler.set_level("00700.HK", SchedulerLevel.HOT)
    assert scheduler.set_level("00700.HK", SchedulerLevel.WARM) is False
    assert scheduler.get_level("00700.HK") is SchedulerLevel.HOT
    clock.advance_monotonic(29.0)
    assert scheduler.set_level("00700.HK", SchedulerLevel.COLD) is False
    clock.advance_monotonic(1.0)
    assert scheduler.set_level("00700.HK", SchedulerLevel.WARM) is True
    assert scheduler.get_level("00700.HK") is SchedulerLevel.WARM


def test_warm_to_cold_requires_longer_dwell() -> None:
    clock, scheduler = _scheduler()
    scheduler.set_level("00700.HK", SchedulerLevel.WARM)
    clock.advance_monotonic(59.0)
    assert scheduler.set_level("00700.HK", SchedulerLevel.COLD) is False
    clock.advance_monotonic(1.0)
    assert scheduler.set_level("00700.HK", SchedulerLevel.COLD) is True


def test_force_bypasses_downgrade_dwell() -> None:
    _, scheduler = _scheduler()
    scheduler.set_level("00700.HK", SchedulerLevel.HOT)
    assert scheduler.set_level("00700.HK", SchedulerLevel.COLD, force=True) is True
    assert scheduler.get_level("00700.HK") is SchedulerLevel.COLD


def test_invalid_level_is_rejected() -> None:
    _, scheduler = _scheduler()
    with pytest.raises(InvalidSchedulerLevelError):
        scheduler.set_level("00700.HK", "BLAZE")  # type: ignore[arg-type]


def test_symbols_maintain_independent_levels() -> None:
    _, scheduler = _scheduler()
    scheduler.set_level("00700.HK", SchedulerLevel.HOT)
    scheduler.set_level("600519.SH", SchedulerLevel.WARM)
    assert scheduler.get_level("00700.HK") is SchedulerLevel.HOT
    assert scheduler.get_level("600519.SH") is SchedulerLevel.WARM


def test_due_symbols_use_monotonic_intervals() -> None:
    clock, scheduler = _scheduler()
    scheduler.set_level("00700.HK", SchedulerLevel.COLD)
    assert scheduler.due_symbols(["00700.HK"]) == ["00700.HK"]
    scheduler.mark_fetched("00700.HK")
    assert scheduler.due_symbols(["00700.HK"]) == []
    clock.advance_monotonic(9.9)
    assert scheduler.due_symbols(["00700.HK"]) == []
    clock.advance_monotonic(0.1)
    assert scheduler.due_symbols(["00700.HK"]) == ["00700.HK"]

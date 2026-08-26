from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import SignalPriority
from market_sentinel.signals.cooldown import CooldownGate


def test_cooldown_suppresses_same_or_lower_priority_inside_window() -> None:
    clock = FakeClock(monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("00700.HK", "volume", SignalPriority.NOTICE) is True
    clock.advance_monotonic(299.0)
    assert gate.allow("00700.HK", "volume", SignalPriority.NOTICE) is False
    assert gate.allow("00700.HK", "volume", SignalPriority.INFO) is False


def test_cooldown_escalation_allows_strictly_higher_priority() -> None:
    clock = FakeClock(monotonic=10.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("00700.HK", "price_volume", SignalPriority.NOTICE) is True
    clock.advance_monotonic(5.0)
    assert gate.allow("00700.HK", "price_volume", SignalPriority.IMPORTANT) is True
    clock.advance_monotonic(5.0)
    assert gate.allow("00700.HK", "price_volume", SignalPriority.IMPORTANT) is False
    assert gate.allow("00700.HK", "price_volume", SignalPriority.CRITICAL) is True


def test_cooldown_expires_on_monotonic_not_wall_time() -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("00700.HK", "breakout", SignalPriority.NOTICE) is True
    clock.advance_wall(400.0)
    assert gate.allow("00700.HK", "breakout", SignalPriority.NOTICE) is False
    clock.advance_monotonic(300.0)
    assert gate.allow("00700.HK", "breakout", SignalPriority.NOTICE) is True


def test_cooldown_is_independent_per_symbol_and_family() -> None:
    clock = FakeClock(monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("00700.HK", "volume", SignalPriority.NOTICE) is True
    assert gate.allow("600519.SH", "volume", SignalPriority.NOTICE) is True
    assert gate.allow("00700.HK", "vwap", SignalPriority.NOTICE) is True
    clock.advance_monotonic(10.0)
    assert gate.allow("00700.HK", "volume", SignalPriority.NOTICE) is False
    assert gate.allow("600519.SH", "volume", SignalPriority.NOTICE) is False
    assert gate.allow("00700.HK", "vwap", SignalPriority.NOTICE) is False

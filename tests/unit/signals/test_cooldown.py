from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import SignalPriority
from market_sentinel.signals.cooldown import CooldownGate


def test_cooldown_suppresses_same_or_lower_priority_inside_window() -> None:
    clock = FakeClock(monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is True
    clock.advance_monotonic(299.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is False
    assert gate.allow("s1", SignalPriority.INFO) is False


def test_cooldown_escalation_allows_strictly_higher_priority() -> None:
    clock = FakeClock(monotonic=10.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is True
    clock.advance_monotonic(5.0)
    assert gate.allow("s1", SignalPriority.IMPORTANT) is True
    clock.advance_monotonic(5.0)
    assert gate.allow("s1", SignalPriority.IMPORTANT) is False
    assert gate.allow("s1", SignalPriority.CRITICAL) is True


def test_cooldown_expires_on_monotonic_not_wall_time() -> None:
    clock = FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is True
    clock.advance_wall(400.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is False
    clock.advance_monotonic(300.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is True


def test_new_episode_id_has_independent_first_alert() -> None:
    clock = FakeClock(monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is True
    clock.advance_monotonic(10.0)
    assert gate.allow("s1", SignalPriority.NOTICE) is False
    assert gate.allow("s2", SignalPriority.NOTICE) is True


def test_up_and_down_episodes_have_independent_first_alerts() -> None:
    clock = FakeClock(monotonic=0.0)
    gate = CooldownGate(clock, cooldown_s=300.0)
    assert gate.allow("tape-up", SignalPriority.INFO) is True
    assert gate.allow("tape-down", SignalPriority.INFO) is True
    clock.advance_monotonic(10.0)
    assert gate.allow("tape-up", SignalPriority.INFO) is False
    assert gate.allow("tape-down", SignalPriority.INFO) is False

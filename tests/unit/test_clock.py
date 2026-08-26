from market_sentinel.clock import FakeClock


def test_advance_moves_wall_and_monotonic() -> None:
    clock = FakeClock(wall=100.0, monotonic=10.0)
    clock.advance(2.5)
    assert clock.wall_time() == 102.5
    assert clock.monotonic_time() == 12.5


def test_set_wall_does_not_change_monotonic() -> None:
    clock = FakeClock(wall=100.0, monotonic=10.0)
    clock.set_wall(500.0)
    assert clock.wall_time() == 500.0
    assert clock.monotonic_time() == 10.0


def test_advance_monotonic_does_not_change_wall() -> None:
    clock = FakeClock(wall=100.0, monotonic=10.0)
    clock.advance_monotonic(3.0)
    assert clock.wall_time() == 100.0
    assert clock.monotonic_time() == 13.0


def test_advance_wall_does_not_change_monotonic() -> None:
    clock = FakeClock(wall=100.0, monotonic=10.0)
    clock.advance_wall(1.0)
    assert clock.wall_time() == 101.0
    assert clock.monotonic_time() == 10.0

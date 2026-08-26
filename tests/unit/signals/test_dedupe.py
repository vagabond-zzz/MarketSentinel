from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.signals.dedupe import EventDeduper
from tests.unit.signals.helpers import make_event


def test_dedupe_suppresses_same_or_lower_severity_inside_ttl() -> None:
    deduper = EventDeduper()
    first = make_event(severity=3, market_timestamp=100.0)
    assert deduper.accept(first) is first
    same = make_event(severity=3, market_timestamp=130.0)
    lower = make_event(severity=2, market_timestamp=140.0)
    assert deduper.accept(same) is None
    assert deduper.accept(lower) is None


def test_dedupe_upgrades_when_severity_is_strictly_higher() -> None:
    deduper = EventDeduper()
    first = make_event(severity=2, market_timestamp=100.0)
    assert deduper.accept(first) is first
    upgraded = make_event(severity=4, market_timestamp=120.0)
    assert deduper.accept(upgraded) is upgraded
    assert deduper.accept(make_event(severity=4, market_timestamp=130.0)) is None
    assert deduper.accept(make_event(severity=3, market_timestamp=140.0)) is None


def test_dedupe_emits_again_after_ttl_expires_at_exact_boundary() -> None:
    deduper = EventDeduper()
    first = make_event(severity=2, market_timestamp=100.0, ttl_s=60.0)
    assert deduper.accept(first) is first
    still_inside = make_event(severity=2, market_timestamp=159.9, ttl_s=60.0)
    assert deduper.accept(still_inside) is None
    expired = make_event(severity=2, market_timestamp=160.0, ttl_s=60.0)
    assert deduper.accept(expired) is expired


def test_dedupe_key_has_no_unix_time_bucket() -> None:
    deduper = EventDeduper()
    # floor(59/60)=0 and floor(61/60)=1 would be different buckets; real TTL suppresses.
    first = make_event(market_timestamp=59.0, ttl_s=60.0)
    second = make_event(market_timestamp=61.0, ttl_s=60.0)
    assert deduper.accept(first) is first
    assert deduper.accept(second) is None
    assert first.dedupe_key == second.dedupe_key
    assert first.dedupe_key == "00700.HK|rapid_move|up"


def test_dedupe_is_independent_per_symbol_type_and_direction() -> None:
    deduper = EventDeduper()
    a = make_event(symbol="00700.HK", market_timestamp=100.0)
    b = make_event(symbol="600519.SH", market_timestamp=101.0)
    down = make_event(direction=EventDirection.DOWN, market_timestamp=102.0)
    volume = make_event(event_type=EventType.VOLUME_SPIKE, market_timestamp=103.0)
    assert deduper.accept(a) is a
    assert deduper.accept(b) is b
    assert deduper.accept(down) is down
    assert deduper.accept(volume) is volume

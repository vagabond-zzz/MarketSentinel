from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventDirection, EventType
from market_sentinel.signals.cluster import cluster_members, partition_lineage_episodes
from market_sentinel.signals.composer import SignalComposer
from tests.unit.events.helpers import make_features
from tests.unit.signals.helpers import make_event


def _compose(direction: EventDirection, ts: float, event_type: EventType = EventType.RAPID_MOVE):
    return make_event(event_type=event_type, direction=direction, market_timestamp=ts)


def test_none_clusters_with_up_and_with_down() -> None:
    composer = SignalComposer(FakeClock())
    volume = _compose(EventDirection.NONE, 10.0, EventType.VOLUME_SPIKE)
    up = _compose(EventDirection.UP, 20.0)
    first, _ = composer.consume(volume, make_features(volume_ratio_5m=1.8))
    joined, _ = composer.consume(up, make_features(change_1m=0.006, volume_ratio_5m=1.8))
    assert joined.id == first.id
    assert joined.direction is EventDirection.UP
    assert volume.id in joined.event_ids

    down_composer = SignalComposer(FakeClock())
    volume_b = _compose(EventDirection.NONE, 10.0, EventType.VOLUME_SPIKE)
    down = _compose(EventDirection.DOWN, 20.0)
    seed, _ = down_composer.consume(volume_b, make_features(volume_ratio_5m=1.8))
    joined_down, _ = down_composer.consume(
        down, make_features(change_1m=-0.006, volume_ratio_5m=1.8)
    )
    assert joined_down.id == seed.id
    assert joined_down.direction is EventDirection.DOWN


def test_same_direction_events_share_an_episode() -> None:
    composer = SignalComposer(FakeClock())
    first, _ = composer.consume(_compose(EventDirection.UP, 10.0), make_features(change_1m=0.006))
    second, _ = composer.consume(
        _compose(EventDirection.UP, 20.0, EventType.DAY_HIGH_BREAKOUT),
        make_features(change_1m=0.006, session_high_ref=100.0, session_high_obs=100.1),
    )
    assert second.id == first.id
    assert {first.direction, second.direction} == {EventDirection.UP}

    down_composer = SignalComposer(FakeClock())
    down1, _ = down_composer.consume(
        _compose(EventDirection.DOWN, 10.0), make_features(change_1m=-0.006)
    )
    down2, _ = down_composer.consume(
        _compose(EventDirection.DOWN, 20.0, EventType.DAY_LOW_BREAKDOWN),
        make_features(change_1m=-0.006, session_low_ref=100.0, session_low_obs=99.9),
    )
    assert down2.id == down1.id
    assert down2.direction is EventDirection.DOWN


def test_up_and_down_do_not_share_a_signal_episode() -> None:
    clock = FakeClock(wall=5.0)
    composer = SignalComposer(clock)
    up, _ = composer.consume(_compose(EventDirection.UP, 10.0), make_features(change_1m=0.006))
    down, _ = composer.consume(_compose(EventDirection.DOWN, 20.0), make_features(change_1m=-0.006))
    assert down.id != up.id
    assert up.direction is EventDirection.UP
    assert down.direction is EventDirection.DOWN
    assert down.event_ids != up.event_ids
    live = composer.active_signals("00700.HK")
    assert {item.direction for item in live} == {EventDirection.UP, EventDirection.DOWN}


def test_cluster_members_keep_none_and_drop_opposite_direction() -> None:
    up = _compose(EventDirection.UP, 10.0)
    down = _compose(EventDirection.DOWN, 20.0)
    none = _compose(EventDirection.NONE, 15.0, EventType.VOLUME_SPIKE)
    members = cluster_members(up, [up, down, none])
    assert down not in members
    assert none in members
    assert up in members
    episodes = partition_lineage_episodes([up, down, none])
    directions = {item[0] for item in episodes}
    assert directions == {EventDirection.UP, EventDirection.DOWN}
    by_dir = dict(episodes)
    assert none in by_dir[EventDirection.UP]
    assert none in by_dir[EventDirection.DOWN]
    assert down not in by_dir[EventDirection.UP]
    assert up not in by_dir[EventDirection.DOWN]

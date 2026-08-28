from __future__ import annotations

from tests.unit.events.helpers import make_features

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import EventType, SignalPriority
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.pipeline import SignalPipeline
from market_sentinel.telemetry.collector import InMemoryTelemetryCollector
from market_sentinel.telemetry.contract import SuppressionReason, TelemetryName
from market_sentinel.telemetry.runtime import TelemetryRuntime, new_run_id


class _DuplicateComposer:
    def __init__(self, inner: SignalComposer, *, duplicate: bool = True) -> None:
        self._inner = inner
        self.duplicate = duplicate

    def consume_batch(self, events, features):  # noqa: ANN001
        produced = self._inner.consume_batch(events, features)
        if self.duplicate and produced:
            return [produced[0], produced[0]]
        return produced

    def prune(self, symbol: str, now_ts: float) -> None:
        self._inner.prune(symbol, now_ts)

    def active_signals(self, symbol: str):  # noqa: ANN201
        return self._inner.active_signals(symbol)

    def trace_for(self, signal_id: str):  # noqa: ANN201
        return self._inner.trace_for(signal_id)


def _runtime(
    clock: FakeClock | None = None,
) -> tuple[FakeClock, InMemoryTelemetryCollector, TelemetryRuntime]:
    clock = clock or FakeClock(wall=10.0, monotonic=0.0)
    memory = InMemoryTelemetryCollector()
    return clock, memory, TelemetryRuntime(clock, memory)


def _events(memory: InMemoryTelemetryCollector, name: TelemetryName) -> list:
    return [item for item in memory.events if item.name is name]


def test_same_runtime_reuses_run_id() -> None:
    clock, memory, runtime = _runtime()
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    pipeline.process(previous, current)
    quiet = make_features(
        market_timestamp=1_700_000_020.0,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    pipeline.process(current, quiet)
    ids = {item.run_id for item in memory.events}
    assert len(ids) == 1
    assert runtime.run_id in ids


def test_new_runtime_has_different_run_id() -> None:
    assert new_run_id() != new_run_id()
    first = TelemetryRuntime(FakeClock())
    second = TelemetryRuntime(FakeClock())
    assert first.run_id != second.run_id


def test_event_generated_once_per_detected_event() -> None:
    clock, memory, runtime = _runtime()
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    generated = _events(memory, TelemetryName.EVENT_GENERATED)
    assert len(generated) == len(result.accepted_events) == 1
    assert generated[0].event_id == result.accepted_events[0].id
    assert generated[0].event_type == EventType.RAPID_MOVE.value


def test_dedupe_emits_event_deduped() -> None:
    clock, memory, runtime = _runtime()
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    first = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    pipeline.process(previous, first)
    second = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    pipeline.process(first, second)
    assert _events(memory, TelemetryName.EVENT_DEDUPED)


def test_multi_event_episode_clusters_once_per_event() -> None:
    clock, memory, runtime = _runtime()
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    clustered = _events(memory, TelemetryName.EVENT_CLUSTERED)
    ids = [item.event_id for item in clustered]
    assert len(ids) == len(set(ids))
    assert set(ids) <= {item.id for item in result.accepted_events}
    assert len(ids) >= 2
    later = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    pipeline.process(current, later)
    again = [item.event_id for item in _events(memory, TelemetryName.EVENT_CLUSTERED)]
    assert again == ids


def test_new_episode_and_priority_escalation() -> None:
    clock, memory, runtime = _runtime()
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    volume = make_features(
        market_timestamp=1_700_000_010.0,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, volume)
    assert _events(memory, TelemetryName.SIGNAL_EPISODE_CREATED)
    assert first.signal_updates[0].priority is SignalPriority.NOTICE
    later = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    second = pipeline.process(volume, later)
    assert second.signal_updates[0].id == first.signal_updates[0].id
    assert _events(memory, TelemetryName.SIGNAL_ESCALATED)


def test_cooldown_suppression_reason() -> None:
    clock, memory, runtime = _runtime()
    pipeline = SignalPipeline(clock, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    seeded = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    pipeline.process(previous, seeded)
    with_breakout = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.1,
    )
    pipeline.process(seeded, with_breakout)
    suppressed = _events(memory, TelemetryName.ALERT_SUPPRESSED)
    assert any(item.suppression_reason is SuppressionReason.COOLDOWN for item in suppressed)


def test_same_tick_duplicate_suppression() -> None:
    clock, memory, runtime = _runtime()
    inner = SignalComposer(clock)
    control_clock = FakeClock(wall=10.0, monotonic=0.0)
    control = SignalPipeline(control_clock)
    pipeline = SignalPipeline(clock, composer=_DuplicateComposer(inner), telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    expected = control.process(previous, current)
    assert len(result.alert_candidates) == len(expected.alert_candidates) == 1
    assert len(result.signal_updates) == len(expected.signal_updates)
    assert [item.priority for item in result.signal_updates] == [
        item.priority for item in expected.signal_updates
    ]
    assert [item.type for item in result.accepted_events] == [
        item.type for item in expected.accepted_events
    ]
    assert len(_events(memory, TelemetryName.SIGNAL_EPISODE_CREATED)) == 1
    assert len(_events(memory, TelemetryName.ALERT_CANDIDATE)) == 1
    dup = [
        item
        for item in _events(memory, TelemetryName.ALERT_SUPPRESSED)
        if item.suppression_reason is SuppressionReason.SAME_TICK_DUPLICATE
    ]
    assert len(dup) == 1


def test_same_tick_duplicate_escalation_observed_once() -> None:
    clock, memory, runtime = _runtime()
    inner = SignalComposer(clock)
    wrapper = _DuplicateComposer(inner, duplicate=False)
    control_clock = FakeClock(wall=10.0, monotonic=0.0)
    control = SignalPipeline(control_clock)
    pipeline = SignalPipeline(clock, composer=wrapper, telemetry=runtime)
    previous = make_features(market_timestamp=1_700_000_000.0)
    volume = make_features(
        market_timestamp=1_700_000_010.0,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    first = pipeline.process(previous, volume)
    control.process(previous, volume)
    assert first.signal_updates[0].priority is SignalPriority.NOTICE
    wrapper.duplicate = True
    later = make_features(
        market_timestamp=1_700_000_020.0,
        change_1m=0.006,
        volume_ratio_5m=1.8,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    second = pipeline.process(volume, later)
    expected = control.process(volume, later)
    assert second.signal_updates[0].id == first.signal_updates[0].id
    assert second.signal_updates[0].priority is SignalPriority.IMPORTANT
    assert len(second.alert_candidates) == len(expected.alert_candidates)
    assert [item.priority for item in second.signal_updates] == [
        item.priority for item in expected.signal_updates
    ]
    assert [item.type for item in second.accepted_events] == [
        item.type for item in expected.accepted_events
    ]
    assert len(_events(memory, TelemetryName.SIGNAL_ESCALATED)) == 1
    assert (
        len(
            [
                item
                for item in _events(memory, TelemetryName.ALERT_SUPPRESSED)
                if item.suppression_reason is SuppressionReason.SAME_TICK_DUPLICATE
            ]
        )
        == 1
    )


def test_collector_failure_does_not_break_pipeline() -> None:
    clock = FakeClock(wall=10.0, monotonic=0.0)

    class Boom:
        def record(self, event: object) -> None:
            raise RuntimeError("collector down")

    pipeline = SignalPipeline(clock, telemetry=TelemetryRuntime(clock, Boom()))
    previous = make_features(market_timestamp=1_700_000_000.0)
    current = make_features(
        market_timestamp=1_700_000_010.0,
        change_1m=0.006,
        session_high_ref=100.0,
        session_high_obs=100.0,
    )
    result = pipeline.process(previous, current)
    assert result.accepted_events
    assert result.alert_candidates


def test_engine_instances_use_distinct_run_ids() -> None:
    from tests.unit.ipc.helpers import make_engine

    _, _, first = make_engine()
    _, _, second = make_engine()
    assert first.telemetry.run_id != second.telemetry.run_id

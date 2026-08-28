from __future__ import annotations

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import SignalPriority
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import Signal, SignalPipelineResult, SignalTrace
from market_sentinel.events.detector import EventDetector
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.cooldown import CooldownGate
from market_sentinel.signals.dedupe import EventDeduper
from market_sentinel.telemetry.contract import (
    SuppressionReason,
    TelemetryName,
)
from market_sentinel.telemetry.runtime import TelemetryRuntime

_PRIORITY_RANK = {
    SignalPriority.INFO: 1,
    SignalPriority.NOTICE: 2,
    SignalPriority.IMPORTANT: 3,
    SignalPriority.CRITICAL: 4,
}


class SignalPipeline:
    """Feature pair → detect all → dedupe all → compose episodes → cooldown once."""

    def __init__(
        self,
        clock: Clock,
        *,
        detector: EventDetector | None = None,
        deduper: EventDeduper | None = None,
        composer: SignalComposer | None = None,
        cooldown: CooldownGate | None = None,
        telemetry: TelemetryRuntime | None = None,
    ) -> None:
        self._detector = detector or EventDetector(clock)
        self._deduper = deduper or EventDeduper()
        self.composer = composer or SignalComposer(clock)
        self._cooldown = cooldown or CooldownGate(clock)
        self._telemetry = telemetry

    def process(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
    ) -> SignalPipelineResult:
        accepted: list[MarketEvent] = []
        for event in self._detector.evaluate(previous, current):
            self._emit_event(TelemetryName.EVENT_GENERATED, event)
            kept = self._deduper.accept(event)
            if kept is not None:
                accepted.append(kept)
            else:
                self._emit_event(TelemetryName.EVENT_DEDUPED, event)
        accepted_events = tuple(accepted)
        prior_priority = {
            item.id: item.priority for item in self.composer.active_signals(current.symbol)
        }
        produced: list[tuple[Signal, SignalTrace]] = []
        if accepted_events:
            produced = self.composer.consume_batch(accepted_events, current)
        else:
            self.composer.prune(current.symbol, current.market_timestamp)
        self._observe_episodes(prior_priority, produced)
        signal_updates = self.composer.active_signals(current.symbol)
        traces = tuple(self.composer.trace_for(item.id) for item in signal_updates)
        seen: set[str] = set()
        alerts: list[Signal] = []
        for signal, _trace in produced:
            if signal.id in seen:
                self._emit_suppressed(signal, SuppressionReason.SAME_TICK_DUPLICATE)
                continue
            seen.add(signal.id)
            if self._cooldown.allow(signal.id, signal.priority):
                alerts.append(signal)
                self._emit_signal(TelemetryName.ALERT_CANDIDATE, signal)
            else:
                self._emit_suppressed(signal, SuppressionReason.COOLDOWN)
        return SignalPipelineResult(
            accepted_events=accepted_events,
            signal_updates=signal_updates,
            traces=traces,
            alert_candidates=tuple(alerts),
        )

    def _observe_episodes(
        self,
        prior_priority: dict[str, SignalPriority],
        produced: list[tuple[Signal, SignalTrace]],
    ) -> None:
        runtime = self._telemetry
        for signal, _trace in produced:
            previous = prior_priority.get(signal.id)
            if previous is None:
                self._emit_signal(TelemetryName.SIGNAL_EPISODE_CREATED, signal)
            elif _PRIORITY_RANK[signal.priority] > _PRIORITY_RANK[previous]:
                self._emit_signal(TelemetryName.SIGNAL_ESCALATED, signal)
            if runtime is None:
                continue
            fresh = runtime.cluster.newly_clustered(signal.event_ids)
            for event_id in fresh:
                runtime.emit(
                    TelemetryName.EVENT_CLUSTERED,
                    symbol=signal.symbol,
                    event_id=event_id,
                    signal_id=signal.id,
                    family=signal.family,
                    direction=signal.direction.value,
                    market_timestamp=signal.market_timestamp,
                )

    def _emit_event(self, name: TelemetryName, event: MarketEvent) -> None:
        if self._telemetry is None:
            return
        self._telemetry.emit(
            name,
            symbol=event.symbol,
            event_id=event.id,
            event_type=event.type.value,
            direction=event.direction.value,
            market_timestamp=event.market_timestamp,
        )

    def _emit_signal(self, name: TelemetryName, signal: Signal) -> None:
        if self._telemetry is None:
            return
        self._telemetry.emit(
            name,
            symbol=signal.symbol,
            signal_id=signal.id,
            family=signal.family,
            direction=signal.direction.value,
            priority=signal.priority.value,
            market_timestamp=signal.market_timestamp,
        )

    def _emit_suppressed(self, signal: Signal, reason: SuppressionReason) -> None:
        if self._telemetry is None:
            return
        self._telemetry.emit(
            TelemetryName.ALERT_SUPPRESSED,
            symbol=signal.symbol,
            signal_id=signal.id,
            family=signal.family,
            direction=signal.direction.value,
            priority=signal.priority.value,
            market_timestamp=signal.market_timestamp,
            suppression_reason=reason,
        )

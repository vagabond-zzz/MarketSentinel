from __future__ import annotations

from market_sentinel.clock import Clock
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import Signal, SignalPipelineResult, SignalTrace
from market_sentinel.events.detector import EventDetector
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.cooldown import CooldownGate
from market_sentinel.signals.dedupe import EventDeduper


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
    ) -> None:
        self._detector = detector or EventDetector(clock)
        self._deduper = deduper or EventDeduper()
        self.composer = composer or SignalComposer(clock)
        self._cooldown = cooldown or CooldownGate(clock)

    def process(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
    ) -> SignalPipelineResult:
        accepted: list[MarketEvent] = []
        for event in self._detector.evaluate(previous, current):
            kept = self._deduper.accept(event)
            if kept is not None:
                accepted.append(kept)
        accepted_events = tuple(accepted)
        produced: list[tuple[Signal, SignalTrace]] = []
        if accepted_events:
            produced = self.composer.consume_batch(accepted_events, current)
        else:
            self.composer.prune(current.symbol, current.market_timestamp)
        signal_updates = self.composer.active_signals(current.symbol)
        traces = tuple(self.composer.trace_for(item.id) for item in signal_updates)
        seen: set[str] = set()
        alerts: list[Signal] = []
        for signal, _trace in produced:
            if signal.id in seen:
                continue
            seen.add(signal.id)
            if self._cooldown.allow(signal.id, signal.priority):
                alerts.append(signal)
        return SignalPipelineResult(
            accepted_events=accepted_events,
            signal_updates=signal_updates,
            traces=traces,
            alert_candidates=tuple(alerts),
        )

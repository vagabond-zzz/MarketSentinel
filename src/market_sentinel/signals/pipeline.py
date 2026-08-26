from __future__ import annotations

from market_sentinel.clock import Clock
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import SignalPipelineResult
from market_sentinel.events.detector import EventDetector
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.cooldown import CooldownGate
from market_sentinel.signals.dedupe import EventDeduper


class SignalPipeline:
    """Feature pair → detect all → dedupe all → compose episodes → cooldown once.

    Not wired into MarketEngine (M7).
    """

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
        if not accepted_events:
            return SignalPipelineResult(
                accepted_events=(),
                signal_updates=(),
                traces=(),
                alert_candidates=(),
            )
        self.composer.consume_batch(accepted_events, current)
        signal_updates = self.composer.active_signals(current.symbol)
        traces = tuple(self.composer.trace_for(item.id) for item in signal_updates)
        alert_candidates = tuple(
            signal
            for signal in signal_updates
            if self._cooldown.allow(signal.symbol, signal.family, signal.priority)
        )
        return SignalPipelineResult(
            accepted_events=accepted_events,
            signal_updates=signal_updates,
            traces=traces,
            alert_candidates=alert_candidates,
        )

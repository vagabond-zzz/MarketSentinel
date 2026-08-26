from __future__ import annotations

from market_sentinel.clock import Clock
from market_sentinel.domain.events import MarketEvent
from market_sentinel.domain.features import MarketFeatures
from market_sentinel.domain.signals import Signal, SignalTrace
from market_sentinel.events.detector import EventDetector
from market_sentinel.signals.composer import SignalComposer
from market_sentinel.signals.cooldown import CooldownGate
from market_sentinel.signals.dedupe import EventDeduper


class SignalPipeline:
    """Feature pair → rules → dedupe → immediate cluster/compose → cooldown.

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
        self._composer = composer or SignalComposer(clock)
        self._cooldown = cooldown or CooldownGate(clock)

    def process(
        self,
        previous: MarketFeatures | None,
        current: MarketFeatures,
    ) -> tuple[list[MarketEvent], Signal | None, SignalTrace | None]:
        accepted: list[MarketEvent] = []
        emitted: Signal | None = None
        emitted_trace: SignalTrace | None = None
        for event in self._detector.evaluate(previous, current):
            kept = self._deduper.accept(event)
            if kept is None:
                continue
            accepted.append(kept)
            signal, trace = self._composer.consume(kept, current)
            if self._cooldown.allow(signal.symbol, signal.family, signal.priority):
                emitted = signal
                emitted_trace = trace
        return accepted, emitted, emitted_trace

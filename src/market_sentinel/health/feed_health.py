from __future__ import annotations

import logging
from dataclasses import dataclass

from market_sentinel.clock import Clock
from market_sentinel.domain.enums import FeedStatus
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.health.policy import HealthPolicy

logger = logging.getLogger(__name__)

_WORST = {
    FeedStatus.LIVE: 0,
    FeedStatus.DELAYED: 1,
    FeedStatus.STALE: 2,
    FeedStatus.DISCONNECTED: 3,
}


@dataclass
class _SymbolHealth:
    last_success_mono: float | None = None
    consecutive_failures: int = 0
    market_timestamp: float | None = None
    received_timestamp: float | None = None
    last_status: FeedStatus | None = None


class FeedHealthTracker:
    def __init__(self, clock: Clock, policy: HealthPolicy | None = None) -> None:
        self._clock = clock
        self._policy = policy or HealthPolicy()
        self._symbols: dict[str, _SymbolHealth] = {}

    def observe(
        self,
        symbol: str,
        snapshot: MarketSnapshot | None = None,
        *,
        error: Exception | None = None,
    ) -> FeedStatus:
        record = self._symbols.setdefault(symbol, _SymbolHealth())
        if snapshot is not None:
            record.last_success_mono = self._clock.monotonic_time()
            record.consecutive_failures = 0
            record.market_timestamp = snapshot.market_timestamp
            record.received_timestamp = snapshot.received_timestamp
            if snapshot.received_timestamp < snapshot.market_timestamp:
                logger.warning(
                    "feed clock skew %s received=%s market=%s",
                    symbol,
                    snapshot.received_timestamp,
                    snapshot.market_timestamp,
                )
        elif error is not None:
            record.consecutive_failures += 1
            logger.warning("provider error %s: %s", symbol, error)
        return self.status(symbol)

    def keep_alive(self, symbol: str) -> None:
        """Freeze a healthy last quote so Replay EOF does not age LIVE → STALE.

        No-op when the symbol never had a successful snapshot, or when a real
        provider/data failure is already recorded. Failures must still age to
        STALE / DISCONNECTED; EOF must not refresh their freshness.
        """
        record = self._symbols.get(symbol)
        if record is None or record.last_success_mono is None:
            return
        if record.consecutive_failures > 0:
            return
        record.last_success_mono = self._clock.monotonic_time()

    def consecutive_failures(self, symbol: str) -> int:
        record = self._symbols.get(symbol)
        return 0 if record is None else record.consecutive_failures

    def peek_status(self, symbol: str) -> FeedStatus:
        return self._compute(self._symbols.get(symbol))

    def status(self, symbol: str) -> FeedStatus:
        record = self._symbols.get(symbol)
        status = self._compute(record)
        if record is not None and record.last_status is not status:
            logger.info(
                "feed health %s %s -> %s",
                symbol,
                record.last_status.value if record.last_status else "NEW",
                status.value,
            )
            record.last_status = status
        return status

    def aggregate_status(self, symbols: list[str]) -> FeedStatus:
        if not symbols:
            return FeedStatus.DISCONNECTED
        return max((self.status(symbol) for symbol in symbols), key=lambda item: _WORST[item])

    def feed_latency(self, symbol: str) -> float | None:
        record = self._symbols.get(symbol)
        if record is None or record.received_timestamp is None or record.market_timestamp is None:
            return None
        return max(0.0, record.received_timestamp - record.market_timestamp)

    def last_update_age(self, symbol: str) -> float | None:
        record = self._symbols.get(symbol)
        if record is None or record.last_success_mono is None:
            return None
        return self._clock.monotonic_time() - record.last_success_mono

    def _compute(self, record: _SymbolHealth | None) -> FeedStatus:
        if record is None:
            return FeedStatus.DISCONNECTED
        if record.last_success_mono is None:
            if record.consecutive_failures >= self._policy.disconnect_failures:
                return FeedStatus.DISCONNECTED
            if record.consecutive_failures > 0:
                return FeedStatus.STALE
            return FeedStatus.DISCONNECTED

        age = self._clock.monotonic_time() - record.last_success_mono
        if (
            record.consecutive_failures >= self._policy.disconnect_failures
            or age >= self._policy.disconnect_s
        ):
            return FeedStatus.DISCONNECTED
        if age >= self._policy.stale_s:
            return FeedStatus.STALE
        latency = self._latency(record)
        if latency >= self._policy.delayed_s:
            return FeedStatus.DELAYED
        return FeedStatus.LIVE

    def _latency(self, record: _SymbolHealth) -> float:
        if record.received_timestamp is None or record.market_timestamp is None:
            return 0.0
        return max(0.0, record.received_timestamp - record.market_timestamp)

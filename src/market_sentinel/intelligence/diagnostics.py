from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class IntelligenceDiagnostics:
    router_decisions: int = 0
    requests_submitted: int = 0
    requests_suppressed: int = 0
    model_calls: int = 0
    fallback_count: int = 0
    timeout_count: int = 0
    parse_failure_count: int = 0
    rate_limit_count: int = 0
    dropped_backpressure: int = 0
    stale_discard: int = 0
    queue_depth: int = 0
    router_decision_latency_s: float = 0.0
    model_latency_s: float = 0.0
    parse_latency_s: float = 0.0
    router_latencies: list[float] = field(default_factory=list)
    model_latencies: list[float] = field(default_factory=list)

    def snapshot(self) -> dict[str, int | float]:
        return {
            "router_decisions": self.router_decisions,
            "requests_submitted": self.requests_submitted,
            "requests_suppressed": self.requests_suppressed,
            "model_calls": self.model_calls,
            "fallback_count": self.fallback_count,
            "timeout_count": self.timeout_count,
            "parse_failure_count": self.parse_failure_count,
            "rate_limit_count": self.rate_limit_count,
            "dropped_backpressure": self.dropped_backpressure,
            "stale_discard": self.stale_discard,
            "queue_depth": self.queue_depth,
            "router_decision_latency_s": self.router_decision_latency_s,
            "model_latency_s": self.model_latency_s,
            "parse_latency_s": self.parse_latency_s,
        }

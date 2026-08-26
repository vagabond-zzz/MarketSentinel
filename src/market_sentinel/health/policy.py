from dataclasses import dataclass


@dataclass(frozen=True)
class HealthPolicy:
    delayed_s: float = 3.0
    stale_s: float = 30.0
    disconnect_s: float = 60.0
    disconnect_failures: int = 3

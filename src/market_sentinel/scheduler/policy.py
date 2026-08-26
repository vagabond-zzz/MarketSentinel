from dataclasses import dataclass


@dataclass(frozen=True)
class SchedulerPolicy:
    cold_interval_s: float = 10.0
    warm_interval_s: float = 3.0
    hot_interval_s: float = 1.0
    upgrade_dwell_s: float = 0.0
    hot_downgrade_dwell_s: float = 30.0
    warm_downgrade_dwell_s: float = 60.0

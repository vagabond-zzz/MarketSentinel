from __future__ import annotations

import math
from collections.abc import Sequence


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def percentile(values: Sequence[float], pct: float) -> float | None:
    """Nearest-rank percentile. Deterministic; valid for small n (report count)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100.0 * len(ordered)))
    return ordered[rank - 1]


def latency_bundle(samples: Sequence[float], stage: str) -> dict[str, object]:
    if not samples:
        return {
            "stage": stage,
            "count": 0,
            "min_s": None,
            "median_s": None,
            "p95_s": None,
            "max_s": None,
        }
    ordered = sorted(samples)
    return {
        "stage": stage,
        "count": len(ordered),
        "min_s": ordered[0],
        "median_s": percentile(ordered, 50),
        "p95_s": percentile(ordered, 95),
        "max_s": ordered[-1],
    }

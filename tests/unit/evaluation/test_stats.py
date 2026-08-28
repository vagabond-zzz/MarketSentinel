from __future__ import annotations

from market_sentinel.evaluation.stats import latency_bundle, percentile, ratio


def test_ratio_zero_denominator_is_none() -> None:
    assert ratio(1, 0) is None
    assert ratio(0, 0) is None
    assert ratio(1, 4) == 0.25


def test_percentile_empty_and_nearest_rank() -> None:
    assert percentile([], 95) is None
    assert percentile([1.0], 95) == 1.0
    assert percentile([0.1, 0.2, 0.3, 0.4, 1.0], 50) == 0.3
    assert percentile([0.1, 0.2, 0.3, 0.4, 1.0], 95) == 1.0


def test_latency_bundle_empty_reports_count() -> None:
    empty = latency_bundle([], "router")
    assert empty["count"] == 0
    assert empty["p95_s"] is None
    assert empty["stage"] == "router"

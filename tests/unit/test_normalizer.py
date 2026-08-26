from __future__ import annotations

from typing import Any

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.errors import SnapshotValidationError
from market_sentinel.market_data.normalizer import normalize_many, normalize_snapshot


def _raw(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": "00700.HK",
        "price": 602.5,
        "open": 595.0,
        "high": 605.0,
        "low": 594.0,
        "prev_close": 595.0,
        "volume": 1_000_000.0,
        "turnover": 602_500_000.0,
        "market_timestamp": 1_700_000_010.0,
    }
    payload.update(overrides)
    return payload


def test_normalize_snapshot_stamps_received_from_wall_clock() -> None:
    clock = FakeClock(wall=1_700_000_050.0, monotonic=9.0)
    snapshot = normalize_snapshot(_raw(), clock)
    assert snapshot.symbol == "00700.HK"
    assert snapshot.price == 602.5
    assert snapshot.market_timestamp == 1_700_000_010.0
    assert snapshot.received_timestamp == 1_700_000_050.0
    assert clock.monotonic_time() == 9.0


def test_normalize_snapshot_rejects_missing_field() -> None:
    raw = _raw()
    del raw["price"]
    with pytest.raises(SnapshotValidationError, match="missing field"):
        normalize_snapshot(raw, FakeClock())


def test_normalize_snapshot_rejects_invalid_timestamp() -> None:
    with pytest.raises(SnapshotValidationError, match="timestamp"):
        normalize_snapshot(_raw(market_timestamp=-1), FakeClock())


def test_normalize_snapshot_rejects_invalid_symbol() -> None:
    with pytest.raises(SnapshotValidationError, match="symbol"):
        normalize_snapshot(_raw(symbol="TENCENT"), FakeClock())


def test_normalize_snapshot_rejects_non_positive_price() -> None:
    with pytest.raises(SnapshotValidationError, match="price"):
        normalize_snapshot(_raw(price=0), FakeClock())


def test_normalize_snapshot_rejects_negative_or_non_finite_turnover() -> None:
    with pytest.raises(SnapshotValidationError, match="turnover"):
        normalize_snapshot(_raw(turnover=-1), FakeClock())
    with pytest.raises(SnapshotValidationError, match="turnover"):
        normalize_snapshot(_raw(turnover=float("nan")), FakeClock())
    with pytest.raises(SnapshotValidationError, match="turnover"):
        normalize_snapshot(_raw(turnover=float("inf")), FakeClock())


def test_normalize_snapshot_accepts_zero_turnover() -> None:
    snapshot = normalize_snapshot(_raw(turnover=0), FakeClock())
    assert snapshot.turnover == 0.0


def test_normalize_many_drops_invalid_rows() -> None:
    clock = FakeClock(wall=1_700_000_100.0)
    snapshots = normalize_many(
        [_raw(), _raw(symbol="BAD"), _raw(symbol="600519.SH", price=1482.3)],
        clock,
    )
    assert [item.symbol for item in snapshots] == ["00700.HK", "600519.SH"]

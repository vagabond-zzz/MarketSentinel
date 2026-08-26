from __future__ import annotations

import logging
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from market_sentinel.clock import Clock
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.errors import SnapshotValidationError

logger = logging.getLogger(__name__)

_SYMBOL_RE = re.compile(r"^[0-9A-Za-z]+\.(SH|SZ|HK)$")
_REQUIRED_FIELDS = (
    "symbol",
    "price",
    "open",
    "high",
    "low",
    "prev_close",
    "volume",
    "market_timestamp",
)


def normalize_snapshot(raw: Mapping[str, Any], clock: Clock) -> MarketSnapshot:
    missing = [field for field in _REQUIRED_FIELDS if field not in raw]
    if missing:
        raise SnapshotValidationError(f"missing field: {missing[0]}")

    symbol = str(raw["symbol"])
    if _SYMBOL_RE.fullmatch(symbol) is None:
        raise SnapshotValidationError(f"invalid symbol: {symbol}")

    price = _require_positive_number(raw["price"], "price")
    open_ = _require_finite_number(raw["open"], "open")
    high = _require_finite_number(raw["high"], "high")
    low = _require_finite_number(raw["low"], "low")
    prev_close = _require_finite_number(raw["prev_close"], "prev_close")
    volume = _require_finite_number(raw["volume"], "volume")
    if volume < 0:
        raise SnapshotValidationError("invalid volume")

    market_timestamp = _require_timestamp(raw["market_timestamp"])
    turnover = None
    if "turnover" in raw and raw["turnover"] is not None:
        turnover = _require_finite_number(raw["turnover"], "turnover")
        if turnover < 0:
            raise SnapshotValidationError("invalid turnover")

    return MarketSnapshot(
        symbol=symbol,
        price=price,
        open=open_,
        high=high,
        low=low,
        prev_close=prev_close,
        volume=volume,
        turnover=turnover,
        market_timestamp=market_timestamp,
        received_timestamp=clock.wall_time(),
    )


def normalize_many(rows: Sequence[Mapping[str, Any]], clock: Clock) -> list[MarketSnapshot]:
    snapshots: list[MarketSnapshot] = []
    for raw in rows:
        try:
            snapshots.append(normalize_snapshot(raw, clock))
        except SnapshotValidationError:
            logger.warning("dropping invalid snapshot: %s", raw.get("symbol", "<unknown>"))
    return snapshots


def _require_positive_number(value: Any, field: str) -> float:
    number = _require_finite_number(value, field)
    if number <= 0:
        raise SnapshotValidationError(f"invalid {field}")
    return number


def _require_timestamp(value: Any) -> float:
    number = _require_finite_number(value, "timestamp")
    if number < 0:
        raise SnapshotValidationError("invalid timestamp")
    return number


def _require_finite_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotValidationError(f"invalid {field}") from exc
    if not math.isfinite(number):
        raise SnapshotValidationError(f"invalid {field}")
    return number

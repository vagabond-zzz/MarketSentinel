from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MIN_INTERVAL_S = 2.0
DEFAULT_INTERVAL_S = 2.0
DEFAULT_SAMPLE_COUNT = 30
ASHARE_SUFFIXES = (".SH", ".SZ")
_SESSION_TZ = timezone(timedelta(hours=8))


class ProbeParseError(ValueError):
    """Probe could not parse a vendor payload. Fail closed."""


class ProbeTransportError(RuntimeError):
    """HTTP/SDK transport failed. Fail closed."""


_BLOCKED_TOKENS = ("访问过于频繁", "forbidden", "access denied", "anti-bot")


def reject_blocked_payload(text: str) -> None:
    lowered = text.lower()
    if any(token in text or token in lowered for token in _BLOCKED_TOKENS):
        raise ProbeTransportError("access-denied")


@dataclass
class Observation:
    provider: str
    symbol: str
    vendor_symbol: str
    received_timestamp: float
    price: float | None
    open: float | None
    high: float | None
    low: float | None
    prev_close: float | None
    volume_raw: float | None
    turnover_raw: float | None
    market_timestamp_raw: str | None
    market_timestamp_parsed: float | None
    trade_status: str | int | None
    field_confidence: dict[str, str]
    received_minus_market_s: float | None = None
    delta_volume: float | None = None
    delta_turnover: float | None = None
    turnover_div_volume: float | None = None
    turnover_div_volume_div_price: float | None = None
    turnover_div_volume_div_100: float | None = None
    turnover_div_volume_times_100: float | None = None
    error: str | None = None
    notes: list[str] = field(default_factory=list)
    name: str | None = None
    field_count: int | None = None

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        return record


def require_ashare(symbol: str) -> str:
    core = symbol.strip().upper()
    if not core.endswith(ASHARE_SUFFIXES):
        raise ProbeParseError(f"M1a probe accepts SH/SZ only, got {symbol}")
    if core.count(".") != 1:
        raise ProbeParseError(f"invalid symbol: {symbol}")
    ticker, suffix = core.split(".")
    if not ticker.isalnum():
        raise ProbeParseError(f"invalid symbol: {symbol}")
    return f"{ticker}.{suffix}"


def clamp_interval(interval_s: float) -> float:
    if interval_s < MIN_INTERVAL_S:
        raise ValueError(f"interval must be >= {MIN_INTERVAL_S}s (got {interval_s})")
    return float(interval_s)


def parse_cst_compact(value: str) -> float:
    text = value.strip()
    if len(text) != 14 or not text.isdigit():
        raise ProbeParseError("timestamp")
    year = int(text[0:4])
    month = int(text[4:6])
    day = int(text[6:8])
    hour = int(text[8:10])
    minute = int(text[10:12])
    second = int(text[12:14])
    try:
        stamp = datetime(year, month, day, hour, minute, second, tzinfo=_SESSION_TZ)
    except ValueError as exc:
        raise ProbeParseError("timestamp") from exc
    return stamp.timestamp()


def require_finite_number(value: object, field: str) -> float:
    if value is None:
        raise ProbeParseError(field)
    text = str(value).strip()
    if text == "":
        raise ProbeParseError(field)
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise ProbeParseError(field) from exc
    if number != number or number in (float("inf"), float("-inf")):
        raise ProbeParseError(field)
    return number


def fill_derived(obs: Observation) -> Observation:
    if obs.market_timestamp_parsed is not None:
        obs.received_minus_market_s = obs.received_timestamp - obs.market_timestamp_parsed
    if obs.turnover_raw is not None and obs.volume_raw not in (None, 0.0):
        ratio = obs.turnover_raw / obs.volume_raw
        obs.turnover_div_volume = ratio
        obs.turnover_div_volume_div_100 = ratio / 100.0
        obs.turnover_div_volume_times_100 = ratio * 100.0
        if obs.price not in (None, 0.0):
            obs.turnover_div_volume_div_price = ratio / obs.price
    return obs


def attach_deltas(rows: list[Observation]) -> list[Observation]:
    previous: dict[str, Observation] = {}
    out: list[Observation] = []
    for row in rows:
        filled = fill_derived(row)
        prior = previous.get(row.symbol)
        if prior is not None and filled.volume_raw is not None and prior.volume_raw is not None:
            filled.delta_volume = filled.volume_raw - prior.volume_raw
        if prior is not None and filled.turnover_raw is not None and prior.turnover_raw is not None:
            filled.delta_turnover = filled.turnover_raw - prior.turnover_raw
        previous[row.symbol] = filled
        out.append(filled)
    return out


def high_low_plausible(
    *,
    price: float,
    open_: float,
    high: float,
    low: float,
) -> tuple[bool, str]:
    if high <= 0 or low <= 0:
        return False, "zero_or_nonpositive_extreme"
    if high < max(open_, price) or low > min(open_, price):
        return False, "inconsistent_with_price_open"
    return True, "LIKELY_session_extreme_not_documented"


def write_jsonl(path: str, rows: list[Observation]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row.to_record(), ensure_ascii=False) + "\n")

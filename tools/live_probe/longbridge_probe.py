from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable
from typing import Any

from tools.live_probe.common import (
    Observation,
    ProbeParseError,
    ProbeTransportError,
    attach_deltas,
    clamp_interval,
    fill_derived,
    require_ashare,
    require_finite_number,
    write_jsonl,
)

_CREDENTIAL_KEYS = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)
_DOCUMENTED = {
    "price": "DOCUMENTED",
    "open": "DOCUMENTED",
    "high": "DOCUMENTED",
    "low": "DOCUMENTED",
    "prev_close": "DOCUMENTED",
    "volume_raw": "DOCUMENTED",
    "turnover_raw": "DOCUMENTED",
    "market_timestamp_raw": "DOCUMENTED",
    "market_timestamp_parsed": "DOCUMENTED",
    "trade_status": "DOCUMENTED",
}


def credentials_present() -> bool:
    return not missing_credential_names()


def missing_credential_names() -> list[str]:
    return [key for key in _CREDENTIAL_KEYS if not os.environ.get(key)]


def _attr(quote: Any, name: str) -> Any:
    if isinstance(quote, dict):
        return quote.get(name)
    return getattr(quote, name, None)


def map_quotes(
    quotes: Iterable[Any],
    *,
    requested: list[str],
    received_timestamp: float,
) -> list[Observation]:
    wanted = [require_ashare(item) for item in requested]
    by_symbol: dict[str, Any] = {}
    for quote in quotes:
        raw_symbol = str(_attr(quote, "symbol") or "")
        core = require_ashare(raw_symbol)
        by_symbol[core] = quote
    rows: list[Observation] = []
    for symbol in wanted:
        quote = by_symbol.get(symbol)
        if quote is None:
            continue
        timestamp = require_finite_number(_attr(quote, "timestamp"), "timestamp")
        row = Observation(
            provider="longbridge",
            symbol=symbol,
            vendor_symbol=str(_attr(quote, "symbol")),
            received_timestamp=received_timestamp,
            price=require_finite_number(_attr(quote, "last_done"), "last_done"),
            open=require_finite_number(_attr(quote, "open"), "open"),
            high=require_finite_number(_attr(quote, "high"), "high"),
            low=require_finite_number(_attr(quote, "low"), "low"),
            prev_close=require_finite_number(_attr(quote, "prev_close"), "prev_close"),
            volume_raw=require_finite_number(_attr(quote, "volume"), "volume"),
            turnover_raw=require_finite_number(_attr(quote, "turnover"), "turnover"),
            market_timestamp_raw=str(_attr(quote, "timestamp")),
            market_timestamp_parsed=timestamp,
            trade_status=_attr(quote, "trade_status"),
            field_confidence=dict(_DOCUMENTED),
            notes=["official QuoteContext.quote fields; volume unit still UNKNOWN"],
        )
        rows.append(fill_derived(row))
    return rows


def fetch_longbridge_quotes(
    symbols: list[str],
    *,
    quote_fn: Callable[[list[str]], Iterable[Any]],
    received_timestamp: float,
) -> list[Observation]:
    cores = [require_ashare(item) for item in symbols]
    try:
        payload = quote_fn(cores)
    except Exception as exc:
        message = str(exc)
        for key in _CREDENTIAL_KEYS:
            secret = os.environ.get(key)
            if secret:
                message = message.replace(secret, "<redacted>")
        raise ProbeTransportError(message) from exc
    return map_quotes(payload, requested=cores, received_timestamp=received_timestamp)


def _sdk_quote_fn() -> Callable[[list[str]], Iterable[Any]]:
    try:
        from longbridge.openapi import Config, QuoteContext
    except ImportError as exc:
        raise ProbeTransportError("longbridge SDK is not installed; uv sync --extra live") from exc
    if not credentials_present():
        missing = ", ".join(missing_credential_names())
        raise ProbeTransportError(f"missing credentials: {missing}")
    try:
        config = Config.from_apikey_env()
        ctx = QuoteContext(config)
    except Exception as exc:
        raise ProbeTransportError("longbridge auth/config failed") from exc
    return ctx.quote


def run_samples(
    symbols: list[str],
    *,
    interval_s: float,
    count: int,
    sleep: Callable[[float], None],
    now: Callable[[], float],
    quote_fn: Callable[[list[str]], Iterable[Any]],
) -> list[Observation]:
    interval = clamp_interval(interval_s)
    if count < 1:
        raise ValueError("count must be >= 1")
    collected: list[Observation] = []
    for index in range(count):
        collected.extend(
            fetch_longbridge_quotes(symbols, quote_fn=quote_fn, received_timestamp=now())
        )
        if index + 1 < count:
            sleep(interval)
    return attach_deltas(collected)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(
        description="Isolated Longbridge A-share quote pull probe. Not a MarketProvider."
    )
    parser.add_argument("--symbols", default="600519.SH,000001.SZ")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if not credentials_present():
        missing = ", ".join(missing_credential_names())
        print(
            "longbridge probe skipped: set "
            f"{missing} in the environment (values are never printed).",
            file=sys.stderr,
        )
        return 0
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    try:
        quote_fn = _sdk_quote_fn()
        rows = run_samples(
            symbols,
            interval_s=args.interval,
            count=args.count,
            sleep=time.sleep,
            now=time.time,
            quote_fn=quote_fn,
        )
    except (ProbeParseError, ProbeTransportError, ValueError) as exc:
        print(f"longbridge probe failed: {exc}", file=sys.stderr)
        return 2
    for row in rows:
        print(json.dumps(row.to_record(), ensure_ascii=False))
    if args.out:
        write_jsonl(args.out, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

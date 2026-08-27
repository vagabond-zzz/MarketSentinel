from __future__ import annotations

import json
import sys
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.live_probe.common import (
    Observation,
    ProbeParseError,
    ProbeTransportError,
    attach_deltas,
    clamp_interval,
    fill_derived,
    parse_cst_compact,
    require_ashare,
    require_finite_number,
    write_jsonl,
)

# Observed 2026-08-27 from https://qt.gtimg.cn/q=sh600519,sz000001
# (88 '~'-fields, compact CST timestamp at index 30).
# Index meanings are INFERRED from field shape + magnitude checks, not official docs.
_INFERRED_INDEX = {
    "price": 3,
    "prev_close": 4,
    "open": 5,
    "timestamp": 30,
    "high": 33,
    "low": 34,
    "volume_raw": 36,
    "turnover_composite": 35,
}
_MIN_FIELDS = 38
_CONFIDENCE = {
    name: "INFERRED"
    for name in (
        "price",
        "open",
        "high",
        "low",
        "prev_close",
        "volume_raw",
        "turnover_raw",
        "market_timestamp_raw",
        "market_timestamp_parsed",
    )
}
ENDPOINT = "https://qt.gtimg.cn/q="


def to_vendor_symbol(symbol: str) -> str:
    core = require_ashare(symbol)
    ticker, suffix = core.split(".")
    return f"{suffix.lower()}{ticker.lower()}"


def _http_get(url: str, timeout_s: float) -> str:
    request = Request(url, headers={"User-Agent": "MarketSentinel-M1a-Probe"})
    try:
        with urlopen(request, timeout=timeout_s) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise ProbeTransportError(f"HTTP {status}")
            raw = response.read()
    except TimeoutError as exc:
        raise ProbeTransportError("timeout") from exc
    except HTTPError as exc:
        raise ProbeTransportError(f"HTTP {exc.code}") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            raise ProbeTransportError("timeout") from exc
        raise ProbeTransportError(f"transport: {reason}") from exc
    for encoding in ("gb18030", "gbk", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ProbeParseError("unable to decode Tencent response")


def parse_tencent_response(text: str, *, requested: list[str]) -> list[Observation]:
    if text.strip() == "":
        raise ProbeParseError("empty")
    wanted = {require_ashare(item): item for item in requested}
    vendor_to_core = {to_vendor_symbol(core): core for core in wanted}
    found: dict[str, Observation] = {}
    for chunk in text.replace("\n", "").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if chunk.startswith("v_pv_none_match"):
            raise ProbeParseError("not found")
        if '="' not in chunk:
            raise ProbeParseError("malformed")
        prefix, body = chunk.split('="', 1)
        body = body.rstrip('";')
        vendor = prefix.removeprefix("v_")
        if vendor not in vendor_to_core:
            continue
        fields = body.split("~")
        if len(fields) < _MIN_FIELDS:
            raise ProbeParseError("field count")
        core = vendor_to_core[vendor]
        composite = fields[_INFERRED_INDEX["turnover_composite"]]
        parts = composite.split("/")
        if len(parts) != 3:
            raise ProbeParseError("turnover")
        timestamp_raw = fields[_INFERRED_INDEX["timestamp"]].strip()
        if timestamp_raw == "":
            raise ProbeParseError("timestamp")
        parsed = parse_cst_compact(timestamp_raw)
        row = Observation(
            provider="tencent",
            symbol=core,
            vendor_symbol=vendor,
            received_timestamp=0.0,
            price=require_finite_number(fields[_INFERRED_INDEX["price"]], "price"),
            open=require_finite_number(fields[_INFERRED_INDEX["open"]], "open"),
            high=require_finite_number(fields[_INFERRED_INDEX["high"]], "high"),
            low=require_finite_number(fields[_INFERRED_INDEX["low"]], "low"),
            prev_close=require_finite_number(fields[_INFERRED_INDEX["prev_close"]], "prev_close"),
            volume_raw=require_finite_number(fields[_INFERRED_INDEX["volume_raw"]], "volume"),
            turnover_raw=require_finite_number(parts[2], "turnover"),
            market_timestamp_raw=timestamp_raw,
            market_timestamp_parsed=parsed,
            trade_status=None,
            field_confidence=dict(_CONFIDENCE),
            notes=[
                "experimental unofficial gtimg HTTP; field indexes INFERRED",
                f"observed_field_count>={len(fields)}",
            ],
        )
        found[core] = row
    missing = [symbol for symbol in wanted if symbol not in found]
    if missing:
        raise ProbeParseError(f"missing symbol: {missing[0]}")
    return [found[require_ashare(item)] for item in requested]


def fetch_tencent_quotes(
    symbols: list[str],
    *,
    transport: Callable[[str, float], str] | None = None,
    timeout_s: float = 8.0,
    received_timestamp: float | None = None,
) -> list[Observation]:
    cores = [require_ashare(item) for item in symbols]
    vendors = [to_vendor_symbol(item) for item in cores]
    url = ENDPOINT + ",".join(vendors)
    getter = transport or _http_get
    try:
        payload = getter(url, timeout_s)
    except TimeoutError as exc:
        raise ProbeTransportError("timeout") from exc
    rows = parse_tencent_response(payload, requested=cores)
    received = received_timestamp
    if received is None:
        import time

        received = time.time()
    stamped: list[Observation] = []
    for row in rows:
        row.received_timestamp = received
        stamped.append(fill_derived(row))
    return stamped


def run_samples(
    symbols: list[str],
    *,
    interval_s: float,
    count: int,
    sleep: Callable[[float], None],
    now: Callable[[], float],
    transport: Callable[[str, float], str] | None = None,
) -> list[Observation]:
    interval = clamp_interval(interval_s)
    if count < 1:
        raise ValueError("count must be >= 1")
    collected: list[Observation] = []
    for index in range(count):
        batch = fetch_tencent_quotes(symbols, transport=transport, received_timestamp=now())
        collected.extend(batch)
        if index + 1 < count:
            sleep(interval)
    return attach_deltas(collected)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(
        description="Isolated experimental Tencent gtimg A-share probe. Not a MarketProvider."
    )
    parser.add_argument("--symbols", default="600519.SH,000001.SZ")
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    try:
        rows = run_samples(
            symbols,
            interval_s=args.interval,
            count=args.count,
            sleep=time.sleep,
            now=time.time,
        )
    except (ProbeParseError, ProbeTransportError, ValueError) as exc:
        print(f"tencent probe failed: {exc}", file=sys.stderr)
        return 2
    for row in rows:
        print(json.dumps(row.to_record(), ensure_ascii=False))
    if args.out:
        write_jsonl(args.out, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

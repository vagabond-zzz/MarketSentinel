from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.live_probe.common import (
    Observation,
    ProbeParseError,
    ProbeTransportError,
    fill_derived,
    reject_blocked_payload,
    require_ashare,
    require_finite_number,
)

ENDPOINT = "https://hq.sinajs.cn/list="
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_BLOCKED = ("访问过于频繁", "forbidden", "access denied")
_CST = timezone(timedelta(hours=8))
_MIN_FIELDS = 32


def to_vendor_symbol(symbol: str) -> str:
    core = require_ashare(symbol)
    ticker, suffix = core.split(".")
    return f"{suffix.lower()}{ticker.lower()}"


def _http_get(url: str, timeout_s: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/",
        },
    )
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
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ProbeParseError("unable to decode Sina response")
    lowered = text.lower()
    if any(token in text or token in lowered for token in _BLOCKED):
        raise ProbeTransportError("access-denied")
    return text


def parse_sina_response(text: str, *, requested: list[str]) -> list[Observation]:
    if text.strip() == "":
        raise ProbeParseError("empty")
    wanted = {require_ashare(item): item for item in requested}
    vendor_to_core = {to_vendor_symbol(core): core for core in wanted}
    found: dict[str, Observation] = {}
    for line in text.splitlines():
        line = line.strip().rstrip(";")
        if not line:
            continue
        if "hq_str_" not in line or '="' not in line:
            raise ProbeParseError("malformed")
        prefix, body = line.split('="', 1)
        body = body.strip('"')
        vendor = prefix.split("hq_str_", 1)[1]
        if vendor not in vendor_to_core:
            continue
        if body.strip() == "":
            raise ProbeParseError("empty quote")
        fields = [part.strip() for part in body.split(",")]
        if len(fields) < _MIN_FIELDS:
            raise ProbeParseError("field count")
        core = vendor_to_core[vendor]
        ticker = core.split(".")[0]
        date_raw = next((item for item in fields if _DATE_RE.match(item)), "")
        time_raw = next((item for item in fields if _TIME_RE.match(item)), "")
        if date_raw == "" or time_raw == "":
            raise ProbeParseError("timestamp")
        name = fields[0]
        if name == "":
            raise ProbeParseError("name")
        stamp = datetime.strptime(f"{date_raw} {time_raw}", "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=_CST
        )
        row = Observation(
            provider="sina",
            symbol=core,
            vendor_symbol=vendor,
            received_timestamp=0.0,
            price=require_finite_number(fields[3], "price"),
            open=require_finite_number(fields[1], "open"),
            high=require_finite_number(fields[4], "high"),
            low=require_finite_number(fields[5], "low"),
            prev_close=require_finite_number(fields[2], "prev_close"),
            volume_raw=require_finite_number(fields[8], "volume"),
            turnover_raw=require_finite_number(fields[9], "amount"),
            market_timestamp_raw=f"{date_raw} {time_raw}",
            market_timestamp_parsed=stamp.timestamp(),
            trade_status=fields[-1] if fields[-1] != "" else None,
            field_confidence={
                "price": "CONVENTIONAL",
                "open": "CONVENTIONAL",
                "high": "CONVENTIONAL",
                "low": "CONVENTIONAL",
                "prev_close": "CONVENTIONAL",
                "volume_raw": "CONVENTIONAL",
                "turnover_raw": "CONVENTIONAL",
                "market_timestamp_raw": "CONVENTIONAL",
            },
            notes=[
                "unofficial hq.sinajs.cn; do not poll aggressively",
                f"observed_field_count={len(fields)}",
                f"ticker={ticker}",
            ],
            name=name,
            field_count=len(fields),
        )
        found[core] = row
    missing = [symbol for symbol in wanted if symbol not in found]
    if missing:
        raise ProbeParseError(f"missing symbol: {missing[0]}")
    return [found[require_ashare(item)] for item in requested]


def fetch_sina_quotes(
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
    reject_blocked_payload(payload)
    rows = parse_sina_response(payload, requested=cores)
    received = received_timestamp
    if received is None:
        import time

        received = time.time()
    stamped: list[Observation] = []
    for row in rows:
        row.received_timestamp = received
        stamped.append(fill_derived(row))
    return stamped


def main(argv: list[str] | None = None) -> int:
    import argparse
    import time

    parser = argparse.ArgumentParser(
        description="One-shot unofficial Sina hq.sinajs.cn cross-check. Not a MarketProvider."
    )
    parser.add_argument("--symbols", default="600519.SH,000001.SZ")
    args = parser.parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    try:
        rows = fetch_sina_quotes(symbols, received_timestamp=time.time())
    except (ProbeParseError, ProbeTransportError, ValueError) as exc:
        print(f"sina probe failed: {exc}", file=sys.stderr)
        return 2
    for row in rows:
        print(json.dumps(row.to_record(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

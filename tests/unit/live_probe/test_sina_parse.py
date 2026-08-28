from __future__ import annotations

import pytest
from tools.live_probe.sina_probe import (
    ProbeParseError,
    ProbeTransportError,
    fetch_sina_quotes,
    parse_sina_response,
    to_vendor_symbol,
)

_HEAD = (
    "Moutai,1289.000,1292.300,1294.400,1296.100,1288.000,1294.350,1294.450,822458,1062741090.000"
)
_SANITIZED = (
    'var hq_str_sh600519="' + _HEAD + "," + ",".join(["0"] * 20) + ',2026-08-28,11:18:06,00,";\n'
)


def test_maps_core_symbol_to_sina_vendor_code() -> None:
    assert to_vendor_symbol("600519.SH") == "sh600519"
    assert to_vendor_symbol("000001.SZ") == "sz000001"


def test_parses_sanitized_sina_line() -> None:
    rows = parse_sina_response(_SANITIZED, requested=["600519.SH"])
    row = rows[0]
    assert row.symbol == "600519.SH"
    assert row.name == "Moutai"
    assert row.price == 1294.4
    assert row.prev_close == 1292.3
    assert row.open == 1289.0
    assert row.high == 1296.1
    assert row.low == 1288.0
    assert row.volume_raw == 822458.0
    assert row.turnover_raw == 1062741090.0
    assert row.market_timestamp_raw == "2026-08-28 11:18:06"
    assert row.field_count is not None and row.field_count >= 32


def test_empty_quote_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="empty quote"):
        parse_sina_response('var hq_str_sh600519="";', requested=["600519.SH"])


def test_short_field_list_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="field count"):
        parse_sina_response('var hq_str_sh600519="Moutai,1,2,3";', requested=["600519.SH"])


def test_missing_symbol_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="missing symbol"):
        parse_sina_response(_SANITIZED, requested=["600519.SH", "000001.SZ"])


def test_access_denied_payload_fails_closed() -> None:
    with pytest.raises(ProbeTransportError, match="access-denied"):
        fetch_sina_quotes(["600519.SH"], transport=lambda _url, _timeout: "访问过于频繁")

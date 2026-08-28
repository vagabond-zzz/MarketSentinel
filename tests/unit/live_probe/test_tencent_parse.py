from __future__ import annotations

import pytest
from tools.live_probe.tencent_probe import (
    ProbeParseError,
    ProbeTransportError,
    fetch_tencent_quotes,
    parse_tencent_response,
    to_vendor_symbol,
)

# Sanitized structural copy of an observed qt.gtimg.cn A-share line (ASCII name).
# Index meanings are INFERRED, not a documented contract.
_SANITIZED_SH = (
    'v_sh600519="1~Maotai~600519~1292.30~1302.80~1304.00~24767~10212~14556~'
    "1292.30~70~1292.29~2~1292.27~1~1292.24~3~1292.01~2~1292.36~2~1292.37~8~"
    "1292.38~4~1292.50~16~1292.59~4~~20260827161455~-10.50~-0.81~1305.00~1288.00~"
    "1292.30/24767/3203715661~24767~320372~0.20~19.84~~1305.00~1288.00~1.30~"
    '16154.80~16154.80~6.43~1433.08~1172.52~0.83~44~1293.52~18.14~19.62~";'
)


def test_maps_core_symbol_to_gtimg_vendor_code() -> None:
    assert to_vendor_symbol("600519.SH") == "sh600519"
    assert to_vendor_symbol("000001.SZ") == "sz000001"


def test_rejects_hk_and_us_symbols() -> None:
    with pytest.raises(ProbeParseError, match="SH/SZ"):
        to_vendor_symbol("00700.HK")
    with pytest.raises(ProbeParseError, match="SH/SZ"):
        to_vendor_symbol("AAPL.US")


def test_parses_sanitized_gtimg_line_without_inventing_units() -> None:
    rows = parse_tencent_response(_SANITIZED_SH, requested=["600519.SH"])
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "600519.SH"
    assert row.vendor_symbol == "sh600519"
    assert row.price == 1292.30
    assert row.prev_close == 1302.80
    assert row.open == 1304.00
    assert row.high == 1305.00
    assert row.low == 1288.00
    assert row.volume_raw == 24767.0
    assert row.turnover_raw == 3203715661.0
    assert row.market_timestamp_raw == "20260827161455"
    assert row.market_timestamp_parsed == pytest.approx(1787818495.0)
    assert row.field_confidence["price"] == "INFERRED"
    assert row.field_confidence["volume_raw"] == "INFERRED"
    assert row.field_confidence["turnover_raw"] == "INFERRED"
    assert row.field_confidence["market_timestamp_raw"] == "INFERRED"
    assert row.name == "Maotai"
    assert row.field_count is not None and row.field_count >= 38


def test_empty_response_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="empty"):
        parse_tencent_response("", requested=["600519.SH"])
    with pytest.raises(ProbeParseError, match="empty"):
        parse_tencent_response("   \n", requested=["600519.SH"])


def test_malformed_response_fails_closed() -> None:
    with pytest.raises(ProbeParseError):
        parse_tencent_response("not-a-quote", requested=["600519.SH"])


def test_symbol_mismatch_fails_closed() -> None:
    swapped = _SANITIZED_SH.replace("~600519~", "~000001~", 1)
    with pytest.raises(ProbeParseError, match="symbol mismatch"):
        parse_tencent_response(swapped, requested=["600519.SH"])


def test_unknown_symbol_marker_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="not found"):
        parse_tencent_response('v_pv_none_match="1";', requested=["600519.SH"])


def test_short_field_list_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="field count"):
        parse_tencent_response('v_sh600519="1~Maotai~600519~1292.30";', requested=["600519.SH"])


def test_non_numeric_price_fails_closed() -> None:
    body = _SANITIZED_SH.replace("~1292.30~1302.80~", "~abc~1302.80~", 1)
    with pytest.raises(ProbeParseError, match="price"):
        parse_tencent_response(body, requested=["600519.SH"])


def test_missing_timestamp_fails_closed() -> None:
    body = _SANITIZED_SH.replace("~20260827161455~", "~~")
    with pytest.raises(ProbeParseError, match="timestamp"):
        parse_tencent_response(body, requested=["600519.SH"])


def test_missing_requested_symbol_fails_closed() -> None:
    with pytest.raises(ProbeParseError, match="missing symbol"):
        parse_tencent_response(_SANITIZED_SH, requested=["600519.SH", "000001.SZ"])


def test_extra_trailing_fields_still_parse() -> None:
    extra = _SANITIZED_SH.replace('";', '~extra~fields";', 1)
    rows = parse_tencent_response(extra, requested=["600519.SH"])
    assert rows[0].price == 1292.30
    assert rows[0].volume_raw == 24767.0


def test_access_denied_payload_fails_closed() -> None:
    with pytest.raises(ProbeTransportError, match="access-denied"):
        fetch_tencent_quotes(["600519.SH"], transport=lambda _url, _timeout: "access denied")

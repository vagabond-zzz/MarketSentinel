from __future__ import annotations

from types import SimpleNamespace

import pytest
from tools.live_probe.common import ProbeTransportError
from tools.live_probe.longbridge_probe import (
    ProbeParseError,
    credentials_present,
    fetch_longbridge_quotes,
    map_quotes,
    missing_credential_names,
)


def test_missing_credentials_are_listed_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LONGBRIDGE_APP_KEY", raising=False)
    monkeypatch.delenv("LONGBRIDGE_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGBRIDGE_ACCESS_TOKEN", raising=False)
    assert credentials_present() is False
    assert missing_credential_names() == [
        "LONGBRIDGE_APP_KEY",
        "LONGBRIDGE_APP_SECRET",
        "LONGBRIDGE_ACCESS_TOKEN",
    ]


def test_maps_official_quote_fields_without_unit_conversion() -> None:
    quote = SimpleNamespace(
        symbol="600519.SH",
        last_done="1292.300",
        open="1304.000",
        high="1305.000",
        low="1288.000",
        prev_close="1302.800",
        volume=2476700,
        turnover="3203715661.000",
        timestamp=1787818495,
        trade_status=0,
    )
    rows = map_quotes([quote], requested=["600519.SH"], received_timestamp=1787818500.0)
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "600519.SH"
    assert row.vendor_symbol == "600519.SH"
    assert row.price == 1292.3
    assert row.volume_raw == 2476700.0
    assert row.turnover_raw == 3203715661.0
    assert row.market_timestamp_parsed == 1787818495.0
    assert row.received_minus_market_s == pytest.approx(5.0)
    assert row.field_confidence["price"] == "DOCUMENTED"
    assert row.field_confidence["volume_raw"] == "DOCUMENTED"
    assert row.field_confidence["market_timestamp_parsed"] == "DOCUMENTED"


def test_invalid_last_done_fails_closed() -> None:
    quote = SimpleNamespace(
        symbol="600519.SH",
        last_done="n/a",
        open="1",
        high="1",
        low="1",
        prev_close="1",
        volume=1,
        turnover="1",
        timestamp=1,
        trade_status=0,
    )
    with pytest.raises(ProbeParseError, match="last_done"):
        map_quotes([quote], requested=["600519.SH"], received_timestamp=2.0)


def test_missing_symbol_returns_empty_not_forged() -> None:
    rows = map_quotes([], requested=["600519.SH"], received_timestamp=1.0)
    assert rows == []


def test_cli_skips_cleanly_without_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.live_probe.longbridge_probe import main

    monkeypatch.delenv("LONGBRIDGE_APP_KEY", raising=False)
    monkeypatch.delenv("LONGBRIDGE_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGBRIDGE_ACCESS_TOKEN", raising=False)
    assert main(["--count", "1"]) == 0
    err = capsys.readouterr().err
    assert "skipped" in err
    assert "LONGBRIDGE_APP_KEY" in err
    assert "xxxxxxx" not in err


def test_rejects_non_ashare_request() -> None:
    with pytest.raises(ProbeParseError, match="SH/SZ"):
        map_quotes([], requested=["00700.HK"], received_timestamp=1.0)


def test_timeout_sdk_and_rate_limit_fail_closed() -> None:
    def boom(_symbols: list[str]) -> list[object]:
        raise TimeoutError("timed out")

    with pytest.raises(ProbeTransportError, match="timed out"):
        fetch_longbridge_quotes(["600519.SH"], quote_fn=boom, received_timestamp=1.0)

    def sdk_error(_symbols: list[str]) -> list[object]:
        raise RuntimeError("quote context closed")

    with pytest.raises(ProbeTransportError, match="quote context closed"):
        fetch_longbridge_quotes(["600519.SH"], quote_fn=sdk_error, received_timestamp=1.0)

    def rate_limited(_symbols: list[str]) -> list[object]:
        raise RuntimeError("301606 rate limit exceeded")

    with pytest.raises(ProbeTransportError, match="301606"):
        fetch_longbridge_quotes(["600519.SH"], quote_fn=rate_limited, received_timestamp=1.0)


def test_auth_failure_does_not_print_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "secret-key-value")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret-secret-value")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "secret-token-value")

    def leak(_symbols: list[str]) -> list[object]:
        raise RuntimeError("auth failed secret-token-value")

    with pytest.raises(ProbeTransportError, match="<redacted>") as caught:
        fetch_longbridge_quotes(["600519.SH"], quote_fn=leak, received_timestamp=1.0)
    assert "secret-token-value" not in str(caught.value)

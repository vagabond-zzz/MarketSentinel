from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from market_sentinel.providers.factory import HTTP_STUB_MESSAGE, create_provider
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider, redact_secrets


def _quote(**overrides: object) -> SimpleNamespace:
    payload = dict(
        symbol="600519.SH",
        last_done="1292.30",
        open="1304.00",
        high="1305.00",
        low="1288.00",
        prev_close="1302.80",
        volume=24767,
        turnover="3203715661.000",
        timestamp=1_700_000_010,
        trade_status=0,
    )
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _provider(quotes: list[object], **kwargs: object) -> LongbridgeQuoteProvider:
    clock = FakeClock(wall=1_700_000_050.0, monotonic=1.0)
    return LongbridgeQuoteProvider(clock, quote_fn=lambda _symbols: quotes, **kwargs)


async def test_valid_sh_and_sz_batch() -> None:
    provider = _provider([_quote(), _quote(symbol="000001.SZ", last_done="11.59", volume=975702)])
    snapshots = await provider.fetch_quotes(["600519.SH", "000001.SZ"])
    assert [item.symbol for item in snapshots] == ["600519.SH", "000001.SZ"]
    assert snapshots[0].price == 1292.3
    assert snapshots[1].price == 11.59
    assert snapshots[0].volume == 24767.0
    assert snapshots[0].turnover is None
    assert snapshots[0].market_timestamp == 1_700_000_010
    assert snapshots[0].received_timestamp == 1_700_000_050.0


async def test_received_timestamp_comes_from_clock_not_vendor() -> None:
    vendor_time = 99.0
    provider = _provider([_quote(timestamp=vendor_time)])
    snapshots = await provider.fetch_quotes(["600519.SH"])
    assert snapshots[0].market_timestamp == vendor_time
    assert snapshots[0].received_timestamp == 1_700_000_050.0
    assert snapshots[0].received_timestamp != snapshots[0].market_timestamp


async def test_missing_symbol_omits_row() -> None:
    provider = _provider([_quote()])
    snapshots = await provider.fetch_quotes(["600519.SH", "000001.SZ"])
    assert [item.symbol for item in snapshots] == ["600519.SH"]


async def test_partial_batch_keeps_valid_symbol() -> None:
    provider = _provider([_quote(), _quote(symbol="000001.SZ", last_done="n/a")])
    snapshots = await provider.fetch_quotes(["600519.SH", "000001.SZ"])
    assert [item.symbol for item in snapshots] == ["600519.SH"]
    assert provider.diagnostics.dropped_symbol_count == 1


async def test_invalid_price_is_dropped() -> None:
    provider = _provider([_quote(last_done="bad")])
    assert await provider.fetch_quotes(["600519.SH"]) == []


async def test_invalid_high_low_is_dropped() -> None:
    zero = _provider([_quote(high="0", low="0")])
    inverted = _provider([_quote(high="10", low="20")])
    assert await zero.fetch_quotes(["600519.SH"]) == []
    assert await inverted.fetch_quotes(["600519.SH"]) == []


async def test_negative_volume_is_dropped() -> None:
    provider = _provider([_quote(volume=-1)])
    assert await provider.fetch_quotes(["600519.SH"]) == []


async def test_bad_timestamp_is_dropped() -> None:
    provider = _provider([_quote(timestamp=-1)])
    assert await provider.fetch_quotes(["600519.SH"]) == []


async def test_turnover_disabled_when_unsafe() -> None:
    provider = _provider([_quote()])
    snapshots = await provider.fetch_quotes(["600519.SH"])
    assert snapshots[0].turnover is None


async def test_hk_symbol_is_not_fetched() -> None:
    called: list[list[str]] = []

    def quote_fn(symbols: list[str]) -> list[object]:
        called.append(symbols)
        return [_quote()]

    provider = LongbridgeQuoteProvider(FakeClock(), quote_fn=quote_fn)
    snapshots = await provider.fetch_quotes(["00700.HK", "600519.SH"])
    assert called == [["600519.SH"]]
    assert [item.symbol for item in snapshots] == ["600519.SH"]


def test_missing_credentials_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LONGBRIDGE_APP_KEY", raising=False)
    monkeypatch.delenv("LONGBRIDGE_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGBRIDGE_ACCESS_TOKEN", raising=False)
    with pytest.raises(ProviderAuthError, match="missing"):
        LongbridgeQuoteProvider(FakeClock())


async def test_transport_exception_is_classified() -> None:
    def boom(_symbols: list[str]) -> list[object]:
        raise RuntimeError("server 301602")

    provider = LongbridgeQuoteProvider(FakeClock(), quote_fn=boom)
    with pytest.raises(ProviderUnavailableError, match="301602"):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.request_failure == 1


async def test_rate_limit_exception() -> None:
    def boom(_symbols: list[str]) -> list[object]:
        raise RuntimeError("301606 rate limit exceeded")

    provider = LongbridgeQuoteProvider(FakeClock(), quote_fn=boom)
    with pytest.raises(ProviderRateLimitError, match="301606"):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.rate_limit_count == 1
    assert provider.diagnostics.request_failure == 1


async def test_secret_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "secret-key-value")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret-secret-value")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "secret-token-value")

    def boom(_symbols: list[str]) -> list[object]:
        raise RuntimeError("auth failed secret-token-value")

    provider = LongbridgeQuoteProvider(FakeClock(), quote_fn=boom)
    with pytest.raises(ProviderAuthError) as caught:
        await provider.fetch_quotes(["600519.SH"])
    assert "secret-token-value" not in str(caught.value)
    assert "<redacted>" in str(caught.value)
    assert redact_secrets("x secret-token-value y") == "x <redacted> y"


async def test_timeout_does_not_return_snapshot() -> None:
    def slow(_symbols: list[str]) -> list[object]:
        time.sleep(0.2)
        return [_quote()]

    provider = LongbridgeQuoteProvider(FakeClock(), quote_fn=slow, timeout_s=0.05)
    with pytest.raises(TimeoutError, match="timeout"):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.timeout_count == 1


def test_http_stub_is_explicit() -> None:
    with pytest.raises(ValueError, match="not implemented"):
        create_provider("http", FakeClock())
    assert "longbridge" in HTTP_STUB_MESSAGE


def test_factory_longbridge_with_injected_transport() -> None:
    provider = create_provider(
        "longbridge",
        FakeClock(),
        quote_fn=lambda _symbols: [_quote()],
    )
    assert isinstance(provider, LongbridgeQuoteProvider)


def test_factory_rejects_unknown_and_replay_without_path() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        create_provider("nope", FakeClock())
    with pytest.raises(ValueError, match="replay"):
        create_provider("replay", FakeClock())

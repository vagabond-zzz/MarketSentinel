from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.errors import (
    ProviderAuthError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
)
from market_sentinel.providers.factory import HTTP_STUB_MESSAGE, create_provider
from market_sentinel.providers.longbridge import (
    MISSING_SDK_MESSAGE,
    LongbridgeQuoteProvider,
    classify_transport_error,
    extract_vendor_error_code,
    redact_secrets,
    vendor_quote_to_raw,
    vendor_timestamp_to_unix,
)


class _CodedError(Exception):
    def __init__(self, code: int, message: str = "") -> None:
        super().__init__(message or str(code))
        self.code = code


def _quote_symbol(quote: object) -> str:
    if isinstance(quote, dict):
        return str(quote.get("symbol") or "")
    return str(getattr(quote, "symbol", "") or "")


class StaticClient:
    def __init__(
        self,
        quotes: list[object] | None = None,
        *,
        error: BaseException | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.quotes = quotes or []
        self.error = error
        self.delay_s = delay_s
        self.calls: list[list[str]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def quote(self, symbols: list[str]) -> list[object]:
        self.calls.append(list(symbols))
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            if self.error is not None:
                raise self.error
            wanted = set(symbols)
            return [quote for quote in self.quotes if _quote_symbol(quote) in wanted]
        finally:
            self.in_flight -= 1


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
    return LongbridgeQuoteProvider(clock, quote_client=StaticClient(quotes), **kwargs)


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


async def test_aware_datetime_timestamp_converts_to_exact_epoch() -> None:
    utc = datetime(2024, 1, 15, 1, 30, 0, tzinfo=UTC)
    cst = datetime(2024, 1, 15, 9, 30, 0, tzinfo=timezone(timedelta(hours=8)))
    assert utc.timestamp() == cst.timestamp()
    assert vendor_timestamp_to_unix(utc) == pytest.approx(1705282200.0)
    assert vendor_timestamp_to_unix(cst) == pytest.approx(1705282200.0)
    provider = _provider([_quote(timestamp=cst)])
    snapshots = await provider.fetch_quotes(["600519.SH"])
    assert snapshots[0].market_timestamp == pytest.approx(1705282200.0)
    assert snapshots[0].received_timestamp == 1_700_000_050.0


def test_naive_datetime_is_fail_closed() -> None:
    naive = datetime(2024, 1, 15, 9, 30, 0)
    assert vendor_timestamp_to_unix(naive) is None


async def test_naive_datetime_quote_is_dropped() -> None:
    provider = _provider([_quote(timestamp=datetime(2024, 1, 15, 9, 30, 0))])
    assert await provider.fetch_quotes(["600519.SH"]) == []
    assert provider.diagnostics.dropped_symbol_count == 1


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


async def test_turnover_always_none() -> None:
    provider = _provider([_quote()])
    snapshots = await provider.fetch_quotes(["600519.SH"])
    assert snapshots[0].turnover is None
    assert vendor_quote_to_raw(_quote())["turnover"] is None
    assert "include_turnover" not in inspect.signature(vendor_quote_to_raw).parameters
    assert "include_turnover" not in inspect.signature(LongbridgeQuoteProvider.__init__).parameters


async def test_hk_symbol_is_not_fetched() -> None:
    client = StaticClient([_quote()])
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client)
    snapshots = await provider.fetch_quotes(["00700.HK", "600519.SH"])
    assert client.calls == [["600519.SH"]]
    assert [item.symbol for item in snapshots] == ["600519.SH"]


def test_missing_credentials_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LONGBRIDGE_APP_KEY", raising=False)
    monkeypatch.delenv("LONGBRIDGE_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGBRIDGE_ACCESS_TOKEN", raising=False)
    with pytest.raises(ProviderAuthError, match="missing"):
        LongbridgeQuoteProvider(FakeClock())


@pytest.mark.parametrize(
    ("code", "exc_type"),
    [
        (301606, ProviderRateLimitError),
        (429001, ProviderRateLimitError),
        (429002, ProviderRateLimitError),
        (401003, ProviderAuthError),
        (403201, ProviderAuthError),
        (403203, ProviderAuthError),
        (403205, ProviderAuthError),
        (301604, ProviderAuthError),
        (301603, ProviderNoDataError),
        (301602, ProviderUnavailableError),
        (500000, ProviderUnavailableError),
    ],
)
def test_error_codes_are_classified(code: int, exc_type: type[Exception]) -> None:
    classified = classify_transport_error(_CodedError(code, f"vendor {code}"))
    assert isinstance(classified, exc_type)
    assert not (code == 301603 and isinstance(classified, ProviderAuthError))


async def test_no_quote_code_is_not_auth() -> None:
    client = StaticClient(error=_CodedError(301603, "no quotes"))
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client)
    with pytest.raises(ProviderNoDataError):
        await provider.fetch_quotes(["600519.SH"])


async def test_rate_limit_exception() -> None:
    client = StaticClient(error=_CodedError(301606, "rate limit exceeded"))
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client)
    with pytest.raises(ProviderRateLimitError, match="301606"):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.rate_limit_count == 1
    assert provider.diagnostics.request_failure == 1


async def test_secret_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "secret-key-value")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "secret-secret-value")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "secret-token-value")
    client = StaticClient(error=_CodedError(401003, "token expired secret-token-value"))
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client)
    with pytest.raises(ProviderAuthError) as caught:
        await provider.fetch_quotes(["600519.SH"])
    assert "secret-token-value" not in str(caught.value)
    assert "<redacted>" in str(caught.value)
    assert redact_secrets("x secret-token-value y") == "x <redacted> y"


async def test_timeout_does_not_return_snapshot() -> None:
    client = StaticClient([_quote()], delay_s=0.2)
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client, timeout_s=0.05)
    with pytest.raises(TimeoutError, match="timeout"):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.timeout_count == 1


async def test_single_flight_lock() -> None:
    client = StaticClient([_quote()], delay_s=0.05)
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client)
    await asyncio.gather(
        provider.fetch_quotes(["600519.SH"]),
        provider.fetch_quotes(["000001.SZ"]),
    )
    assert client.max_in_flight == 1


async def test_sdk_context_reused_then_recreated_after_connection_failure() -> None:
    creates = {"n": 0}

    class Ctx:
        def __init__(self) -> None:
            self.fail_next = False

        async def quote(self, symbols: list[str]) -> list[object]:
            if self.fail_next:
                raise ConnectionError("broken pipe")
            return [_quote()]

    current: dict[str, Ctx] = {}

    def factory() -> Ctx:
        creates["n"] += 1
        ctx = Ctx()
        current["ctx"] = ctx
        return ctx

    provider = LongbridgeQuoteProvider(FakeClock(), sdk_factory=factory)
    first = await provider.fetch_quotes(["600519.SH"])
    second = await provider.fetch_quotes(["600519.SH"])
    assert len(first) == 1 and len(second) == 1
    assert provider.diagnostics.context_create_count == 1
    current["ctx"].fail_next = True
    with pytest.raises(ProviderUnavailableError):
        await provider.fetch_quotes(["600519.SH"])
    third = await provider.fetch_quotes(["600519.SH"])
    assert len(third) == 1
    assert provider.diagnostics.context_create_count == 2
    assert creates["n"] == 2


async def test_timeout_discards_sdk_context_before_next_fetch() -> None:
    creates = {"n": 0}

    class SlowCtx:
        async def quote(self, symbols: list[str]) -> list[object]:
            await asyncio.sleep(0.2)
            return [_quote()]

    def factory() -> SlowCtx:
        creates["n"] += 1
        return SlowCtx()

    provider = LongbridgeQuoteProvider(FakeClock(), sdk_factory=factory, timeout_s=0.05)
    with pytest.raises(TimeoutError):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.context_create_count == 1
    with pytest.raises(TimeoutError):
        await provider.fetch_quotes(["600519.SH"])
    assert provider.diagnostics.context_create_count == 2


async def test_missing_sdk_is_actionable() -> None:
    def factory() -> Any:
        raise ImportError("longbridge")

    provider = LongbridgeQuoteProvider(
        FakeClock(),
        sdk_factory=factory,
    )
    with pytest.raises(ProviderUnavailableError, match="uv sync --extra live"):
        await provider.fetch_quotes(["600519.SH"])


def test_http_stub_is_explicit() -> None:
    with pytest.raises(ValueError, match="not implemented"):
        create_provider("http", FakeClock())
    assert "longbridge" in HTTP_STUB_MESSAGE


def test_factory_longbridge_with_injected_transport() -> None:
    provider = create_provider(
        "longbridge",
        FakeClock(),
        quote_client=StaticClient([_quote()]),
    )
    assert isinstance(provider, LongbridgeQuoteProvider)


def test_factory_rejects_unknown_and_replay_without_path() -> None:
    with pytest.raises(ValueError, match="unknown provider"):
        create_provider("nope", FakeClock())
    with pytest.raises(ValueError, match="replay"):
        create_provider("replay", FakeClock())


def test_sdk_like_exception_code_is_preferred_over_message() -> None:
    class SdkError(Exception):
        def __init__(self, kind: object, code: int, message: str) -> None:
            super().__init__(f"(kind={kind}, code={code}) {message}")
            self.kind = kind
            self.code = code

    exc = SdkError("OpenApi", 301603, "no quotes")
    assert extract_vendor_error_code(exc) == 301603
    classified = classify_transport_error(exc)
    assert isinstance(classified, ProviderNoDataError)
    assert not isinstance(classified, ProviderAuthError)


def test_no_quote_text_fallback_is_not_auth() -> None:
    classified = classify_transport_error(RuntimeError("vendor returned no quotes"))
    assert isinstance(classified, ProviderNoDataError)
    assert not isinstance(classified, ProviderAuthError)


def test_production_quote_path_is_native_async() -> None:
    source = (
        Path(__file__).resolve().parents[2] / "src/market_sentinel/providers/longbridge.py"
    ).read_text(encoding="utf-8")
    assert "asyncio.to_thread" not in source
    assert "QuoteContext(" not in source
    assert "AsyncQuoteContext.create" in source
    assert "include_turnover" not in source
    fetch_src = inspect.getsource(LongbridgeQuoteProvider.fetch_quotes)
    assert "to_thread" not in fetch_src
    assert "asyncio.Lock" in inspect.getsource(LongbridgeQuoteProvider.__init__)
    assert "wait_for" in fetch_src


async def test_one_two_and_ten_symbol_batches() -> None:
    ten = [
        "600519.SH",
        "000001.SZ",
        "600036.SH",
        "601318.SH",
        "000858.SZ",
        "002415.SZ",
        "600276.SH",
        "000333.SZ",
        "601166.SH",
        "600900.SH",
    ]
    quotes = [_quote(symbol=symbol, last_done="10.00", volume=1) for symbol in ten]
    client = StaticClient(quotes)
    provider = LongbridgeQuoteProvider(FakeClock(), quote_client=client)
    one = await provider.fetch_quotes(ten[:1])
    two = await provider.fetch_quotes(ten[:2])
    all_ten = await provider.fetch_quotes(ten)
    assert [item.symbol for item in one] == ten[:1]
    assert [item.symbol for item in two] == ten[:2]
    assert [item.symbol for item in all_ten] == ten
    assert client.calls[0] == ten[:1]
    assert client.calls[1] == ten[:2]
    assert client.calls[2] == ten
    assert all(item.turnover is None for item in (*one, *two, *all_ten))


def test_missing_sdk_at_construction_is_actionable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "k")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "s")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "t")

    def missing() -> None:
        raise ProviderUnavailableError(MISSING_SDK_MESSAGE)

    monkeypatch.setattr(
        "market_sentinel.providers.longbridge._require_installed_sdk",
        missing,
    )
    with pytest.raises(ProviderUnavailableError, match="uv sync --extra live"):
        LongbridgeQuoteProvider(FakeClock())

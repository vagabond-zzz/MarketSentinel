from __future__ import annotations

import asyncio
import logging
import math
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from market_sentinel.clock import Clock
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderNoDataError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    SnapshotValidationError,
)
from market_sentinel.market_data.normalizer import normalize_snapshot

logger = logging.getLogger(__name__)

CREDENTIAL_KEYS = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)
ASHARE_SUFFIXES = (".SH", ".SZ")
DEFAULT_TIMEOUT_S = 8.0
MISSING_SDK_MESSAGE = "longbridge SDK is not installed; run uv sync --extra live"
RATE_LIMIT_CODES = frozenset({301606, 429001, 429002})
AUTH_CODES = frozenset({401003, 403201, 403203, 403205, 301604})
NO_DATA_CODES = frozenset({301603})
SERVER_CODES = frozenset({301602, 500000})
_CODE_RE = re.compile(r"\b(30160[0-9]|301604|301606|401003|40320[135]|42900[12]|500000)\b")


class QuoteClient(Protocol):
    """Async Longbridge quote transport. One in-flight quote() per provider."""

    async def quote(self, symbols: list[str]) -> Sequence[Any]: ...


@dataclass
class ProviderDiagnostics:
    request_success: int = 0
    request_failure: int = 0
    last_request_latency_s: float | None = None
    timeout_count: int = 0
    rate_limit_count: int = 0
    last_market_timestamp: float | None = None
    last_received_timestamp: float | None = None
    dropped_symbol_count: int = 0
    context_create_count: int = 0
    notes: list[str] = field(default_factory=list)


def missing_credential_names() -> list[str]:
    return [key for key in CREDENTIAL_KEYS if not os.environ.get(key)]


def credentials_present() -> bool:
    return not missing_credential_names()


def redact_secrets(message: str) -> str:
    redacted = message
    for key in CREDENTIAL_KEYS:
        secret = os.environ.get(key)
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return redacted


def is_ashare(symbol: str) -> bool:
    return symbol.endswith(ASHARE_SUFFIXES) and symbol.count(".") == 1


def _attr(quote: Any, name: str) -> Any:
    if isinstance(quote, dict):
        return quote.get(name)
    return getattr(quote, name, None)


def vendor_timestamp_to_unix(value: object) -> float | None:
    """Convert a Longbridge quote timestamp to Unix seconds.

    Timezone-aware datetime uses ``datetime.timestamp()``. Numeric values are
    allowed for test seams. Naive datetime is fail-closed (None).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.timestamp()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def extract_vendor_error_code(exc: BaseException) -> int | None:
    for attr in ("code", "error_code"):
        raw = getattr(exc, attr, None)
        if callable(raw):
            try:
                raw = raw()
            except TypeError:
                continue
        if isinstance(raw, int) and raw > 0:
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    match = _CODE_RE.search(redact_secrets(str(exc)))
    if match is None:
        return None
    return int(match.group(1))


def classify_transport_error(exc: BaseException) -> ProviderError:
    text = redact_secrets(str(exc))
    code = extract_vendor_error_code(exc)
    message = text if code is None or str(code) in text else f"{code} {text}"
    if code in RATE_LIMIT_CODES:
        return ProviderRateLimitError(message)
    if code in AUTH_CODES:
        return ProviderAuthError(message)
    if code in NO_DATA_CODES:
        return ProviderNoDataError(message)
    if code in SERVER_CODES:
        return ProviderUnavailableError(message)
    lowered = text.lower()
    if "429001" in text or "429002" in text or "rate limit" in lowered:
        return ProviderRateLimitError(message)
    if "no quote" in lowered:
        return ProviderNoDataError(message)
    if any(
        token in lowered
        for token in (
            "token expired",
            "signature invalid",
            "apikey illegal",
            "ip is not allowed",
            "no access",
        )
    ):
        return ProviderAuthError(message)
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return ProviderUnavailableError(message)
    return ProviderUnavailableError(message)


def extract_vendor_fields(quote: Any) -> dict[str, Any]:
    """Pull documented Longbridge quote attributes. No unit conversion."""
    symbol = str(_attr(quote, "symbol") or "")
    return {
        "symbol": symbol,
        "price": _attr(quote, "last_done"),
        "open": _attr(quote, "open"),
        "high": _attr(quote, "high"),
        "low": _attr(quote, "low"),
        "prev_close": _attr(quote, "prev_close"),
        "volume": _attr(quote, "volume"),
        "turnover": _attr(quote, "turnover"),
        "market_timestamp": _attr(quote, "timestamp"),
        "trade_status": _attr(quote, "trade_status"),
    }


def vendor_quote_to_raw(quote: Any) -> dict[str, Any] | None:
    fields = extract_vendor_fields(quote)
    symbol = str(fields["symbol"])
    if not is_ashare(symbol):
        return None
    timestamp = vendor_timestamp_to_unix(fields["market_timestamp"])
    if timestamp is None:
        return None
    try:
        high = float(fields["high"])
        low = float(fields["low"])
    except (TypeError, ValueError):
        return None
    if high <= 0 or low <= 0 or high < low:
        return None
    return {
        "symbol": symbol,
        "price": fields["price"],
        "open": fields["open"],
        "high": fields["high"],
        "low": fields["low"],
        "prev_close": fields["prev_close"],
        "volume": fields["volume"],
        "market_timestamp": timestamp,
        "turnover": None,
    }


class _SdkQuoteClient:
    def __init__(self, context: Any) -> None:
        self.context = context

    async def quote(self, symbols: list[str]) -> Sequence[Any]:
        return await self.context.quote(symbols)


class LongbridgeQuoteProvider:
    """Official Longbridge quote-pull adapter. Not a Tencent fallback.

    Production owns one process-lifetime ``AsyncQuoteContext`` (lazy). There is
    no documented close(); child-process exit is final cleanup.
    """

    def __init__(
        self,
        clock: Clock,
        *,
        quote_client: QuoteClient | None = None,
        sdk_factory: Any | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._clock = clock
        self._quote_client = quote_client
        self._sdk_factory = sdk_factory
        self._timeout_s = timeout_s
        self._sdk_client: QuoteClient | None = None
        self._flight = asyncio.Lock()
        self.diagnostics = ProviderDiagnostics()
        if quote_client is None and sdk_factory is None:
            if not credentials_present():
                missing = ", ".join(missing_credential_names())
                raise ProviderAuthError(
                    f"missing {missing}; set environment variables (values are never logged)"
                )
            _require_installed_sdk()

    async def fetch_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        requested = [symbol for symbol in symbols if is_ashare(symbol)]
        if not requested:
            return []
        started = self._clock.monotonic_time()
        async with self._flight:
            try:
                client = self._quote_client or await self._ensure_sdk_client()
                payload = await asyncio.wait_for(client.quote(requested), timeout=self._timeout_s)
            except TimeoutError as exc:
                self._invalidate_sdk("timeout")
                self.diagnostics.timeout_count += 1
                self.diagnostics.request_failure += 1
                self.diagnostics.last_request_latency_s = self._clock.monotonic_time() - started
                logger.warning("longbridge quote timeout")
                raise TimeoutError("longbridge quote timeout") from exc
            except ProviderRateLimitError:
                self.diagnostics.rate_limit_count += 1
                self.diagnostics.request_failure += 1
                self.diagnostics.last_request_latency_s = self._clock.monotonic_time() - started
                raise
            except ProviderError:
                self.diagnostics.request_failure += 1
                self.diagnostics.last_request_latency_s = self._clock.monotonic_time() - started
                raise
            except Exception as exc:
                classified = classify_transport_error(exc)
                if self._is_fatal_connection(exc, classified):
                    self._invalidate_sdk("connection")
                self.diagnostics.request_failure += 1
                if isinstance(classified, ProviderRateLimitError):
                    self.diagnostics.rate_limit_count += 1
                    logger.warning("longbridge rate limited")
                else:
                    logger.warning("longbridge transport error")
                self.diagnostics.last_request_latency_s = self._clock.monotonic_time() - started
                raise classified from exc
        snapshots: list[MarketSnapshot] = []
        for quote in payload:
            raw = vendor_quote_to_raw(quote)
            if raw is None:
                self.diagnostics.dropped_symbol_count += 1
                continue
            try:
                snapshot = normalize_snapshot(raw, self._clock)
            except SnapshotValidationError:
                self.diagnostics.dropped_symbol_count += 1
                logger.warning("dropping invalid longbridge quote for %s", raw.get("symbol"))
                continue
            snapshots.append(snapshot)
            self.diagnostics.last_market_timestamp = snapshot.market_timestamp
            self.diagnostics.last_received_timestamp = snapshot.received_timestamp
        self.diagnostics.request_success += 1
        self.diagnostics.last_request_latency_s = self._clock.monotonic_time() - started
        return snapshots

    async def _ensure_sdk_client(self) -> QuoteClient:
        if self._sdk_client is not None:
            return self._sdk_client
        try:
            created = (self._sdk_factory or _create_async_quote_context)()
            if inspect_awaitable(created):
                created = await created
            quote = getattr(created, "quote", None)
            if quote is not None and asyncio.iscoroutinefunction(quote):
                client: QuoteClient = created  # type: ignore[assignment]
            else:
                client = _SdkQuoteClient(created)
        except ProviderError:
            raise
        except ImportError as exc:
            raise ProviderUnavailableError(MISSING_SDK_MESSAGE) from exc
        except Exception as exc:
            raise classify_transport_error(exc) from exc
        self._sdk_client = client
        self.diagnostics.context_create_count += 1
        logger.info("longbridge AsyncQuoteContext created (process lifetime)")
        return client

    def _invalidate_sdk(self, reason: str) -> None:
        if self._quote_client is not None:
            return
        if self._sdk_client is not None:
            logger.warning("discarding longbridge quote context (%s)", reason)
        self._sdk_client = None

    @staticmethod
    def _is_fatal_connection(exc: BaseException, classified: ProviderError) -> bool:
        del classified
        return isinstance(exc, (ConnectionError, OSError))


def inspect_awaitable(value: object) -> bool:
    return asyncio.iscoroutine(value) or asyncio.isfuture(value)


def _require_installed_sdk() -> None:
    try:
        import longbridge.openapi as _openapi
    except ImportError as exc:
        raise ProviderUnavailableError(MISSING_SDK_MESSAGE) from exc
    del _openapi


def _create_async_quote_context() -> Any:
    _require_installed_sdk()
    from longbridge.openapi import AsyncQuoteContext, Config

    return AsyncQuoteContext.create(Config.from_apikey_env())

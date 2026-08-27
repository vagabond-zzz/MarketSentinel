from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from market_sentinel.clock import Clock
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.errors import (
    ProviderAuthError,
    ProviderError,
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
QuoteFn = Callable[[list[str]], Iterable[Any]]


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


def _classify_transport_error(exc: BaseException) -> ProviderError:
    text = redact_secrets(str(exc))
    lowered = text.lower()
    if "301606" in text or "rate limit" in lowered:
        return ProviderRateLimitError(text)
    if (
        "301603" in text
        or "unauthorized" in lowered
        or "auth" in lowered
        or "permission" in lowered
    ):
        return ProviderAuthError(text)
    return ProviderUnavailableError(text)


def vendor_quote_to_raw(
    quote: Any,
    *,
    include_turnover: bool,
) -> dict[str, Any] | None:
    fields = extract_vendor_fields(quote)
    symbol = str(fields["symbol"])
    if not is_ashare(symbol):
        return None
    try:
        high = float(fields["high"])
        low = float(fields["low"])
    except (TypeError, ValueError):
        return None
    if high <= 0 or low <= 0 or high < low:
        return None
    raw: dict[str, Any] = {
        "symbol": symbol,
        "price": fields["price"],
        "open": fields["open"],
        "high": fields["high"],
        "low": fields["low"],
        "prev_close": fields["prev_close"],
        "volume": fields["volume"],
        "market_timestamp": fields["market_timestamp"],
        "turnover": None,
    }
    if include_turnover:
        raw["turnover"] = fields["turnover"]
    return raw


class LongbridgeQuoteProvider:
    """Official Longbridge quote-pull adapter. Not a Tencent fallback."""

    def __init__(
        self,
        clock: Clock,
        *,
        quote_fn: QuoteFn | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        include_turnover: bool = False,
    ) -> None:
        self._clock = clock
        self._quote_fn = quote_fn
        self._timeout_s = timeout_s
        self._include_turnover = include_turnover
        self.diagnostics = ProviderDiagnostics()
        if quote_fn is None and not credentials_present():
            missing = ", ".join(missing_credential_names())
            raise ProviderAuthError(
                f"missing {missing}; set environment variables (values are never logged)"
            )

    async def fetch_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        requested = [symbol for symbol in symbols if is_ashare(symbol)]
        if not requested:
            return []
        started = self._clock.monotonic_time()
        try:
            payload = await asyncio.wait_for(
                asyncio.to_thread(self._pull, requested),
                timeout=self._timeout_s,
            )
        except TimeoutError as exc:
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
        snapshots: list[MarketSnapshot] = []
        for quote in payload:
            raw = vendor_quote_to_raw(quote, include_turnover=self._include_turnover)
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

    def _pull(self, symbols: list[str]) -> Sequence[Any]:
        getter = self._quote_fn or self._sdk_quote
        try:
            return tuple(getter(symbols))
        except ProviderError:
            raise
        except TimeoutError:
            raise
        except Exception as exc:
            classified = _classify_transport_error(exc)
            if isinstance(classified, ProviderRateLimitError):
                logger.warning("longbridge rate limited")
            else:
                logger.warning("longbridge transport error")
            raise classified from exc

    def _sdk_quote(self, symbols: list[str]) -> Sequence[Any]:
        try:
            from longbridge.openapi import Config, QuoteContext
        except ImportError as exc:
            raise ProviderUnavailableError(
                "longbridge SDK is not installed; run uv sync --extra live"
            ) from exc
        try:
            context = QuoteContext(Config.from_apikey_env())
            return tuple(context.quote(symbols))
        except Exception as exc:
            raise _classify_transport_error(exc) from exc

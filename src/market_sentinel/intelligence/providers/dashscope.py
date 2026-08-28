from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_sentinel.intelligence.errors import (
    IntelligenceAuthError,
    IntelligenceMalformedError,
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
    IntelligenceTransportError,
    IntelligenceUnavailableError,
)
from market_sentinel.intelligence.parse import ModelCompletion, parse_model_output

Transport = Callable[[str, dict[str, str], bytes, float], tuple[int, str]]

SYSTEM_PROMPT = (
    "You are a market tape analyst. Reply with a JSON object only, keys: "
    "worth_highlight (bool), reason (string), confidence (0..1), summary (string). "
    "Use only the supplied structured facts. Do not give buy/sell or trading advice. "
    "Do not invent prices, volumes, or events."
)


def _default_transport(
    url: str, headers: dict[str, str], body: bytes, timeout_s: float
) -> tuple[int, str]:
    request = Request(url, data=body, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_s) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read()
    except TimeoutError as exc:
        raise IntelligenceTimeoutError("model request timed out") from exc
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
        return int(exc.code), detail
    except URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        if "timed out" in reason.lower():
            raise IntelligenceTimeoutError("model request timed out") from exc
        raise IntelligenceTransportError("model transport failed") from exc
    for encoding in ("utf-8", "gb18030"):
        try:
            return status, raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IntelligenceMalformedError("unable to decode model response")


class DashScopeIntelligenceProvider:
    """Compatible-mode Chat Completions adapter. Vendor details stay here."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        max_output_tokens: int = 150,
        transport: Transport | None = None,
    ) -> None:
        if api_key.strip() == "":
            raise IntelligenceAuthError("API key is not set")
        self._api_key = api_key
        self._model = model
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._max_output_tokens = max_output_tokens
        self._transport = transport or _default_transport
        self.last_parse_latency_s = 0.0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _raise_http(self, status: int) -> None:
        if status in {401, 403}:
            raise IntelligenceAuthError("model auth failed")
        if status == 429:
            raise IntelligenceRateLimitError("model rate limited")
        if status >= 500:
            raise IntelligenceUnavailableError("model unavailable")
        raise IntelligenceTransportError(f"model HTTP {status}")

    def complete_sync(self, payload: Mapping[str, Any], *, timeout_s: float) -> ModelCompletion:
        body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(dict(payload), ensure_ascii=True)},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": self._max_output_tokens,
                "temperature": 0.2,
                "enable_thinking": False,
            }
        ).encode("utf-8")
        try:
            status, text = self._transport(self._endpoint, self._headers(), body, timeout_s)
        except TimeoutError as exc:
            raise IntelligenceTimeoutError("model request timed out") from exc
        if status >= 400:
            self._raise_http(status)
        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as exc:
            raise IntelligenceMalformedError("model envelope is not JSON") from exc
        try:
            content = envelope["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise IntelligenceMalformedError("model envelope missing content") from exc
        if not isinstance(content, str):
            raise IntelligenceMalformedError("model content is not a string")
        started = time.perf_counter()
        parsed = parse_model_output(content)
        self.last_parse_latency_s = time.perf_counter() - started
        return parsed

    async def complete(self, payload: Mapping[str, Any], *, timeout_s: float) -> ModelCompletion:
        import asyncio

        return await asyncio.to_thread(self.complete_sync, payload, timeout_s=timeout_s)

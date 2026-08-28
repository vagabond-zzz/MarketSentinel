from __future__ import annotations

import json
from inspect import signature

import pytest

from market_sentinel.clock import FakeClock
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.errors import (
    IntelligenceAuthError,
    IntelligenceRateLimitError,
    IntelligenceTimeoutError,
)
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.model_settings import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_S,
    load_model_settings,
)
from market_sentinel.intelligence.providers.dashscope import DashScopeIntelligenceProvider


def _envelope(content: str) -> str:
    return json.dumps({"choices": [{"message": {"content": content}}]})


def test_load_model_settings_uses_dedicated_env_overrides() -> None:
    settings = load_model_settings(
        {
            "MARKET_SENTINEL_INTEL_MODEL": "other-model",
            "MARKET_SENTINEL_INTEL_TIMEOUT_S": "4.5",
        }
    )
    assert settings.model == "other-model"
    assert settings.timeout_s == pytest.approx(4.5)
    assert load_model_settings({}).model == DEFAULT_MODEL
    assert load_model_settings({}).timeout_s == pytest.approx(DEFAULT_TIMEOUT_S)


def test_production_intelligence_timeout_default_is_eight_seconds() -> None:
    assert DEFAULT_TIMEOUT_S == pytest.approx(8.0)
    assert load_model_settings({}).timeout_s == pytest.approx(8.0)
    params = signature(IntelligenceCoordinator.__init__).parameters
    assert params["timeout_s"].default == pytest.approx(8.0)
    assert params["queue_size"].default == 8
    assert params["concurrency"].default == 1
    coordinator = IntelligenceCoordinator(FakeIntelligenceProvider(), FakeClock())
    assert coordinator._timeout_s == pytest.approx(8.0)


def test_dashscope_request_body_disables_thinking_and_keeps_key_out_of_body() -> None:
    captured: dict[str, object] = {}

    def transport(
        url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> tuple[int, str]:
        del timeout_s
        captured["url"] = url
        captured["headers"] = headers
        captured["body"] = json.loads(body.decode("utf-8"))
        content = (
            '{"worth_highlight": true, "reason": "price and volume expanded", '
            '"confidence": 0.7, "summary": "Expansion is strong."}'
        )
        return 200, _envelope(content)

    provider = DashScopeIntelligenceProvider(
        api_key="sk-test-key",
        model=DEFAULT_MODEL,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        transport=transport,
    )
    provider.complete_sync({"symbol": "00700.HK", "priority": "important"}, timeout_s=2.0)
    payload = captured["body"]
    assert isinstance(payload, dict)
    assert payload["model"] == DEFAULT_MODEL
    assert payload["enable_thinking"] is False
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["max_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS
    assert payload["temperature"] == pytest.approx(0.2)
    blob = json.dumps(payload)
    assert "sk-test-key" not in blob
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer sk-test-key"


@pytest.mark.asyncio
async def test_dashscope_parses_injected_transport_without_network() -> None:
    content = (
        '{"worth_highlight": true, "reason": "price and volume expanded", '
        '"confidence": 0.7, "summary": "Expansion is strong."}'
    )

    def transport(
        url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> tuple[int, str]:
        del timeout_s
        assert "chat/completions" in url
        assert "sk-test-key" in headers["Authorization"]
        payload = json.loads(body.decode("utf-8"))
        assert payload["model"] == DEFAULT_MODEL
        assert payload["enable_thinking"] is False
        user = json.loads(payload["messages"][1]["content"])
        assert user["symbol"] == "00700.HK"
        assert "sk-test-key" not in json.dumps(user)
        return 200, _envelope(content)

    provider = DashScopeIntelligenceProvider(
        api_key="sk-test-key",
        model=DEFAULT_MODEL,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        transport=transport,
    )
    row = await provider.complete({"symbol": "00700.HK", "priority": "important"}, timeout_s=2.0)
    assert row.confidence == pytest.approx(0.7)
    assert row.token_in is None
    assert row.token_out is None


def test_dashscope_maps_rate_limit_timeout_and_redacts_key() -> None:
    def limited(
        _url: str, _headers: dict[str, str], _body: bytes, _timeout: float
    ) -> tuple[int, str]:
        return 429, "sk-test-key"

    provider = DashScopeIntelligenceProvider(
        api_key="sk-test-key",
        model=DEFAULT_MODEL,
        base_url="https://example.invalid/v1",
        transport=limited,
    )
    with pytest.raises(IntelligenceRateLimitError, match="rate limited"):
        provider.complete_sync({}, timeout_s=1.0)

    def boom(_url: str, _headers: dict[str, str], _body: bytes, _timeout: float) -> tuple[int, str]:
        raise TimeoutError("timed out")

    timed = DashScopeIntelligenceProvider(
        api_key="sk-test-key",
        model=DEFAULT_MODEL,
        base_url="https://example.invalid/v1",
        transport=boom,
    )
    with pytest.raises(IntelligenceTimeoutError):
        timed.complete_sync({}, timeout_s=1.0)

    with pytest.raises(IntelligenceAuthError, match="not set"):
        DashScopeIntelligenceProvider(api_key="  ", model="x", base_url="https://example.invalid")


def test_dashscope_forwards_provider_usage_when_present() -> None:
    content = (
        '{"worth_highlight": true, "reason": "price and volume expanded", '
        '"confidence": 0.7, "summary": "Expansion is strong."}'
    )

    def transport(
        url: str, headers: dict[str, str], body: bytes, timeout_s: float
    ) -> tuple[int, str]:
        del url, headers, body, timeout_s
        envelope = {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 4},
        }
        return 200, json.dumps(envelope)

    provider = DashScopeIntelligenceProvider(
        api_key="sk-test-key",
        model=DEFAULT_MODEL,
        base_url="https://example.invalid/v1",
        transport=transport,
    )
    row = provider.complete_sync({"symbol": "00700.HK"}, timeout_s=1.0)
    assert row.token_in == 9
    assert row.token_out == 4

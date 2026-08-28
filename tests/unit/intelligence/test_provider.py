from __future__ import annotations

import pytest

from market_sentinel.intelligence.errors import IntelligenceTimeoutError
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.parse import ModelCompletion
from market_sentinel.intelligence.redaction import redact_secrets


@pytest.mark.asyncio
async def test_fake_provider_is_scriptable_and_records_payload() -> None:
    scripted = ModelCompletion(True, "reason", 0.5, "summary")
    provider = FakeIntelligenceProvider(scripted)
    payload = {"symbol": "00700.HK", "priority": "important"}
    out = await provider.complete(payload, timeout_s=1.0)
    assert out == scripted
    assert provider.calls == [payload]


@pytest.mark.asyncio
async def test_fake_provider_can_raise_timeout() -> None:
    provider = FakeIntelligenceProvider(error=IntelligenceTimeoutError("timeout"))
    with pytest.raises(IntelligenceTimeoutError):
        await provider.complete({"symbol": "x"}, timeout_s=0.1)


def test_redact_secrets_strips_api_key() -> None:
    text = redact_secrets("Authorization Bearer sk-secret-value failed", ("sk-secret-value",))
    assert "sk-secret-value" not in text
    assert "[redacted]" in text

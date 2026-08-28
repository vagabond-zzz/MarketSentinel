from __future__ import annotations

import os

from market_sentinel.intelligence.errors import IntelligenceAuthError
from market_sentinel.intelligence.fake import FakeIntelligenceProvider
from market_sentinel.intelligence.model_settings import (
    IntelligenceModelSettings,
    load_model_settings,
)
from market_sentinel.intelligence.provider import IntelligenceProvider


def create_intelligence_provider(
    name: str | None = None,
    *,
    settings: IntelligenceModelSettings | None = None,
    api_key: str | None = None,
    environ: dict[str, str] | None = None,
) -> IntelligenceProvider:
    env = os.environ if environ is None else environ
    resolved = settings or load_model_settings(dict(env))
    chosen = (name or resolved.provider).strip().lower()
    if chosen == "fake":
        return FakeIntelligenceProvider()
    if chosen == "dashscope":
        from market_sentinel.intelligence.providers.dashscope import DashScopeIntelligenceProvider

        key = api_key if api_key is not None else env.get(resolved.api_key_env, "")
        if not key:
            raise IntelligenceAuthError("API key is not set")
        return DashScopeIntelligenceProvider(
            api_key=key,
            model=resolved.model,
            base_url=resolved.base_url,
            max_output_tokens=resolved.max_output_tokens,
        )
    raise ValueError(f"unknown intelligence provider: {chosen}")

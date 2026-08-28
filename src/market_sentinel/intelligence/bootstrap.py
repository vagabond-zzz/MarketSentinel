from __future__ import annotations

import os
from collections.abc import Mapping

from market_sentinel.clock import Clock
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.factory import create_intelligence_provider
from market_sentinel.intelligence.model_settings import load_model_settings


def optional_intelligence(
    clock: Clock,
    *,
    environ: Mapping[str, str] | None = None,
) -> IntelligenceCoordinator | None:
    env = os.environ if environ is None else environ
    flag = str(env.get("MARKET_SENTINEL_INTEL_ENABLED", "")).strip().lower()
    if flag not in {"1", "true", "yes"}:
        return None
    settings = load_model_settings(dict(env))
    name = env.get("MARKET_SENTINEL_INTEL_PROVIDER", settings.provider)
    key = env.get(settings.api_key_env, "") if name.strip().lower() != "fake" else ""
    provider = create_intelligence_provider(
        name, settings=settings, api_key=key or None, environ=dict(env)
    )
    return IntelligenceCoordinator(
        provider,
        clock,
        timeout_s=settings.timeout_s,
        secrets=(key,) if key else (),
    )

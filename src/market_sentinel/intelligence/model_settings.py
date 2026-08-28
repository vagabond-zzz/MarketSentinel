from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_PROVIDER = "dashscope"
DEFAULT_MODEL = "qwen3.7-max-2026-06-08"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_TIMEOUT_S = 8.0
DEFAULT_MAX_OUTPUT_TOKENS = 150
API_KEY_ENV = "DASHSCOPE_API_KEY"


@dataclass(frozen=True)
class IntelligenceModelSettings:
    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    api_key_env: str = API_KEY_ENV


def load_model_settings(environ: Mapping[str, str] | None = None) -> IntelligenceModelSettings:
    env = os.environ if environ is None else environ
    timeout_raw = env.get("MARKET_SENTINEL_INTEL_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))
    tokens_raw = env.get("MARKET_SENTINEL_INTEL_MAX_OUTPUT_TOKENS", str(DEFAULT_MAX_OUTPUT_TOKENS))
    return IntelligenceModelSettings(
        provider=env.get("MARKET_SENTINEL_INTEL_PROVIDER", DEFAULT_PROVIDER),
        model=env.get("MARKET_SENTINEL_INTEL_MODEL", DEFAULT_MODEL),
        base_url=env.get("MARKET_SENTINEL_INTEL_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        timeout_s=float(timeout_raw),
        max_output_tokens=int(tokens_raw),
        api_key_env=env.get("MARKET_SENTINEL_INTEL_API_KEY_ENV", API_KEY_ENV),
    )

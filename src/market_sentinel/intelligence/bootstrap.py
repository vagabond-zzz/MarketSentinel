from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from market_sentinel.clock import Clock
from market_sentinel.intelligence.coordinator import IntelligenceCoordinator
from market_sentinel.intelligence.errors import IntelligenceError
from market_sentinel.intelligence.factory import create_intelligence_provider
from market_sentinel.intelligence.model_settings import load_model_settings
from market_sentinel.intelligence.redaction import redact_secrets
from market_sentinel.telemetry.runtime import TelemetryRuntime

logger = logging.getLogger(__name__)


def optional_intelligence(
    clock: Clock,
    *,
    environ: Mapping[str, str] | None = None,
    telemetry: TelemetryRuntime | None = None,
    enabled: bool | None = None,
) -> IntelligenceCoordinator | None:
    env = os.environ if environ is None else environ
    if enabled is False:
        return None
    if enabled is None:
        flag = str(env.get("MARKET_SENTINEL_INTEL_ENABLED", "")).strip().lower()
        if flag not in {"1", "true", "yes"}:
            return None
    secret = ""
    try:
        settings = load_model_settings(dict(env))
        name = str(env.get("MARKET_SENTINEL_INTEL_PROVIDER", settings.provider))
        secret = str(env.get(settings.api_key_env, "")) if name.strip().lower() != "fake" else ""
        provider = create_intelligence_provider(
            name, settings=settings, api_key=secret or None, environ=dict(env)
        )
        return IntelligenceCoordinator(
            provider,
            clock,
            timeout_s=settings.timeout_s,
            secrets=(secret,) if secret else (),
            telemetry=telemetry,
        )
    except (IntelligenceError, ValueError) as exc:
        logger.warning(
            "intelligence sidecar disabled; continuing Rule-only: %s",
            redact_secrets(str(exc), (secret,) if secret else ()),
        )
        return None

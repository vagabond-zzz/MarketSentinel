from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from market_sentinel.intelligence.parse import ModelCompletion


class IntelligenceProvider(Protocol):
    """Vendor-agnostic model adapter. Domain code must not import SDKs here."""

    async def complete(
        self, payload: Mapping[str, Any], *, timeout_s: float
    ) -> ModelCompletion: ...

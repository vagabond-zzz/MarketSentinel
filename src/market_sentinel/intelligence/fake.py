from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from market_sentinel.intelligence.parse import ModelCompletion


class FakeIntelligenceProvider:
    def __init__(
        self,
        scripted: ModelCompletion | None = None,
        *,
        error: BaseException | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self.scripted = scripted or ModelCompletion(
            worth_highlight=True,
            reason="scripted",
            confidence=0.5,
            summary="scripted summary",
        )
        self.error = error
        self.delay_s = delay_s
        self.calls: list[Mapping[str, Any]] = []

    async def complete(self, payload: Mapping[str, Any], *, timeout_s: float) -> ModelCompletion:
        del timeout_s
        self.calls.append(payload)
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return self.scripted

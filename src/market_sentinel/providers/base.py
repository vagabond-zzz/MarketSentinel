from __future__ import annotations

from typing import Protocol

from market_sentinel.domain.models import MarketSnapshot


class MarketProvider(Protocol):
    async def fetch_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        """Fetch quotes for the given symbols. Partial results are allowed."""

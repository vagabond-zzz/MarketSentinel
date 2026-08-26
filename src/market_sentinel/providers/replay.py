from __future__ import annotations

import json
from pathlib import Path

from market_sentinel.clock import Clock
from market_sentinel.domain.models import MarketSnapshot
from market_sentinel.market_data.normalizer import normalize_many


class ReplayProvider:
    def __init__(self, path: Path, clock: Clock) -> None:
        self._clock = clock
        self._ticks = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self._index = 0

    async def fetch_quotes(self, symbols: list[str]) -> list[MarketSnapshot]:
        if self._index >= len(self._ticks):
            return []
        batch = self._ticks[self._index]
        self._index += 1
        wanted = set(symbols)
        return [
            snapshot for snapshot in normalize_many(batch, self._clock) if snapshot.symbol in wanted
        ]

from __future__ import annotations

from market_sentinel.intelligence.contract import IntelligenceResult


class AnnotationRegistry:
    def __init__(self) -> None:
        self._rows: dict[str, IntelligenceResult] = {}

    def get(self, signal_id: str) -> IntelligenceResult | None:
        return self._rows.get(signal_id)

    def put(self, result: IntelligenceResult) -> None:
        self._rows[result.signal_id] = result

    def drop(self, signal_id: str) -> None:
        self._rows.pop(signal_id, None)

    def clear(self) -> None:
        self._rows.clear()

    def ids(self) -> set[str]:
        return set(self._rows)

    def prune(self, active_ids: set[str]) -> None:
        stale = [key for key in self._rows if key not in active_ids]
        for key in stale:
            self._rows.pop(key, None)

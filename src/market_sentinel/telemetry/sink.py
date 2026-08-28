from __future__ import annotations

from typing import Protocol


class TelemetrySink(Protocol):
    def write(self, record: dict[str, object]) -> None: ...

    def close(self) -> None: ...

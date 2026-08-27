from __future__ import annotations

import json
from typing import Any, TextIO


class ProtocolWriter:
    """Sole stdout writer for daemon protocol lines."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def send(self, message: dict[str, Any]) -> None:
        self._stream.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._stream.flush()

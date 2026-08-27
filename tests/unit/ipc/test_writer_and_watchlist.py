from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_sentinel.domain.models import WatchItem
from market_sentinel.errors import WatchlistFullError, WatchlistSymbolError
from market_sentinel.ipc.writer import ProtocolWriter
from market_sentinel.watchlist.watchlist import Watchlist


class _TrackingStdout:
    def __init__(self) -> None:
        self.ops: list[tuple[str, str | None]] = []
        self.chunks: list[str] = []

    def write(self, text: str) -> int:
        self.ops.append(("write", text))
        self.chunks.append(text)
        return len(text)

    def flush(self) -> None:
        self.ops.append(("flush", None))


def test_writer_flushes_after_each_line() -> None:
    stream = _TrackingStdout()
    ProtocolWriter(stream).send({"protocol_version": 1, "type": "ack"})
    assert stream.ops[0][0] == "write"
    assert stream.ops[1] == ("flush", None)
    assert stream.chunks[0].endswith("\n")
    json.loads(stream.chunks[0])


def test_runtime_watchlist_does_not_write_json(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    watchlist = Watchlist(path, persist=False)
    watchlist.add("00700.HK")
    watchlist.replace([WatchItem("600519.SH", True)])
    assert not path.exists()


def test_replace_overwrites_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    watchlist = Watchlist(path)
    watchlist.add("00700.HK")
    watchlist.replace([WatchItem("600519.SH", False)])
    restored = Watchlist(path)
    items = {item.symbol: item.enabled for item in restored.list()}
    assert items == {"600519.SH": False}


def test_replace_duplicate_and_limit() -> None:
    watchlist = Watchlist(persist=False)
    with pytest.raises(WatchlistSymbolError):
        watchlist.replace([WatchItem("A"), WatchItem("A")])
    with pytest.raises(WatchlistFullError):
        watchlist.replace([WatchItem(f"s{index}") for index in range(11)])

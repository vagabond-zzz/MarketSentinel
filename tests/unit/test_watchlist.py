from pathlib import Path

import pytest

from market_sentinel.errors import WatchlistFullError, WatchlistSymbolError
from market_sentinel.watchlist.watchlist import Watchlist


def test_add_list_and_duplicate_is_idempotent(tmp_path: Path) -> None:
    watchlist = Watchlist(tmp_path / "watchlist.json")
    first = watchlist.add("00700.HK")
    watchlist.disable("00700.HK")
    duplicate = watchlist.add("00700.HK")
    assert first.symbol == "00700.HK"
    assert duplicate.enabled is False
    assert [item.symbol for item in watchlist.list()] == ["00700.HK"]


def test_limit_ten_raises(tmp_path: Path) -> None:
    watchlist = Watchlist(tmp_path / "watchlist.json")
    for index in range(10):
        watchlist.add(f"60000{index}.SH")
    with pytest.raises(WatchlistFullError):
        watchlist.add("00700.HK")


def test_remove_enable_disable_and_enabled_symbols(tmp_path: Path) -> None:
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add("00700.HK")
    watchlist.add("600519.SH")
    watchlist.disable("00700.HK")
    assert watchlist.enabled_symbols() == ["600519.SH"]
    watchlist.enable("00700.HK")
    assert set(watchlist.enabled_symbols()) == {"00700.HK", "600519.SH"}
    watchlist.remove("600519.SH")
    assert [item.symbol for item in watchlist.list()] == ["00700.HK"]


def test_remove_missing_symbol_raises(tmp_path: Path) -> None:
    watchlist = Watchlist(tmp_path / "watchlist.json")
    with pytest.raises(WatchlistSymbolError):
        watchlist.remove("00700.HK")


def test_enable_disable_missing_symbol_raises(tmp_path: Path) -> None:
    watchlist = Watchlist(tmp_path / "watchlist.json")
    with pytest.raises(WatchlistSymbolError):
        watchlist.enable("00700.HK")
    with pytest.raises(WatchlistSymbolError):
        watchlist.disable("00700.HK")


def test_persists_to_json_and_reloads(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    watchlist = Watchlist(path)
    watchlist.add("00700.HK")
    watchlist.add("600519.SH")
    watchlist.disable("600519.SH")
    restored = Watchlist(path)
    items = {item.symbol: item.enabled for item in restored.list()}
    assert items == {"00700.HK": True, "600519.SH": False}

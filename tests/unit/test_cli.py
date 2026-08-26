from pathlib import Path

from market_sentinel.cli.display import format_dashboard
from market_sentinel.cli.main import main
from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.domain.models import MarketSnapshot, MarketState
from market_sentinel.watchlist.watchlist import Watchlist


def test_format_dashboard_includes_core_diagnostics() -> None:
    snapshot = MarketSnapshot(
        symbol="00700.HK",
        price=602.5,
        open=595.0,
        high=605.0,
        low=594.0,
        prev_close=595.0,
        volume=1.0,
        turnover=None,
        market_timestamp=1.0,
        received_timestamp=1.8,
    )
    state = MarketState(
        symbol="00700.HK",
        latest=snapshot,
        level=SchedulerLevel.WARM,
        feed_status=FeedStatus.LIVE,
        feed_latency=0.2,
        last_update_age=0.8,
    )
    text = format_dashboard(FeedStatus.LIVE, [state], watchlist_count=10)
    assert "MARKET SENTINEL" in text
    assert "Feed: LIVE" in text
    assert "Watchlist: 10" in text
    assert "00700.HK" in text
    assert "602.50" in text
    assert "+1.26%" in text
    assert "WARM" in text
    assert "age=0.8s" in text
    assert "lat=0.2s" in text


def test_cli_watchlist_add_persists(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    restored = Watchlist(path)
    assert [item.symbol for item in restored.list()] == ["00700.HK"]

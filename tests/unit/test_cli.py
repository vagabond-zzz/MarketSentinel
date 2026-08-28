from pathlib import Path

import pytest

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
    assert "00700.HK  WARM" in text
    assert "602.50" in text
    assert "Age          0.80s" in text
    assert "Latency      0.20s" in text
    assert "ACTIVE SIGNALS" in text
    assert "EVENTS THIS TICK" in text
    assert "ALERTS THIS TICK" in text
    assert "None" in text


def test_cli_watchlist_add_persists(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    restored = Watchlist(path)
    assert [item.symbol for item in restored.list()] == ["00700.HK"]


def test_run_once_prints_state_events_and_alerts(tmp_path: Path, capsys) -> None:
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    capsys.readouterr()
    assert main(["--watchlist", str(path), "run", "--once"]) == 0
    out = capsys.readouterr().out
    assert "MARKET SENTINEL" in out
    assert "00700.HK  COLD" in out
    assert "ACTIVE SIGNALS" in out
    assert "EVENTS THIS TICK" in out
    assert "ALERTS THIS TICK" in out
    assert "Updated:" in out
    assert "\x1b[" not in out


def test_http_provider_is_not_implemented(tmp_path: Path, capsys) -> None:
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "--provider", "http", "run", "--once"]) == 2
    err = capsys.readouterr().err
    assert "HttpQuoteProvider is not implemented; use fake, replay, or longbridge." in err


def test_longbridge_provider_requires_credentials(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LONGBRIDGE_APP_KEY", raising=False)
    monkeypatch.delenv("LONGBRIDGE_APP_SECRET", raising=False)
    monkeypatch.delenv("LONGBRIDGE_ACCESS_TOKEN", raising=False)
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "--provider", "longbridge", "run", "--once"]) == 2
    err = capsys.readouterr().err
    assert "LONGBRIDGE_APP_KEY" in err
    assert "LONGBRIDGE_ACCESS_TOKEN" in err


def test_longbridge_missing_sdk_is_actionable(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    from market_sentinel.errors import ProviderUnavailableError
    from market_sentinel.providers.longbridge import MISSING_SDK_MESSAGE

    monkeypatch.setenv("LONGBRIDGE_APP_KEY", "k")
    monkeypatch.setenv("LONGBRIDGE_APP_SECRET", "s")
    monkeypatch.setenv("LONGBRIDGE_ACCESS_TOKEN", "t")

    def missing() -> None:
        raise ProviderUnavailableError(MISSING_SDK_MESSAGE)

    monkeypatch.setattr(
        "market_sentinel.providers.longbridge._require_installed_sdk",
        missing,
    )
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "--provider", "longbridge", "run", "--once"]) == 2
    err = capsys.readouterr().err
    assert "uv sync --extra live" in err


def test_run_once_survives_intelligence_missing_key(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARKET_SENTINEL_INTEL_ENABLED", "1")
    monkeypatch.setenv("MARKET_SENTINEL_INTEL_PROVIDER", "dashscope")
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    capsys.readouterr()
    assert main(["--watchlist", str(path), "run", "--once"]) == 0
    captured = capsys.readouterr()
    assert "MARKET SENTINEL" in captured.out
    assert "API key" not in captured.out
    assert captured.out.strip().startswith("MARKET SENTINEL") or "Feed:" in captured.out


def test_run_once_survives_unknown_intelligence_provider(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARKET_SENTINEL_INTEL_ENABLED", "1")
    monkeypatch.setenv("MARKET_SENTINEL_INTEL_PROVIDER", "not-a-vendor")
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    capsys.readouterr()
    assert main(["--watchlist", str(path), "run", "--once"]) == 0
    out = capsys.readouterr().out
    assert "MARKET SENTINEL" in out


def test_run_once_starts_and_shuts_down_fake_intelligence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from market_sentinel.intelligence.coordinator import IntelligenceCoordinator

    events: list[str] = []
    orig_start = IntelligenceCoordinator.start
    orig_idle = IntelligenceCoordinator.idle
    orig_shutdown = IntelligenceCoordinator.shutdown

    async def start(self) -> None:
        events.append("start")
        await orig_start(self)

    async def idle(self) -> None:
        events.append("idle")
        await orig_idle(self)

    async def shutdown(self) -> None:
        events.append("shutdown")
        await orig_shutdown(self)

    monkeypatch.setattr(IntelligenceCoordinator, "start", start)
    monkeypatch.setattr(IntelligenceCoordinator, "idle", idle)
    monkeypatch.setattr(IntelligenceCoordinator, "shutdown", shutdown)
    monkeypatch.setenv("MARKET_SENTINEL_INTEL_ENABLED", "1")
    monkeypatch.setenv("MARKET_SENTINEL_INTEL_PROVIDER", "fake")
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    assert main(["--watchlist", str(path), "run", "--once"]) == 0
    assert events[:1] == ["start"]
    assert "idle" in events
    assert events[-1] == "shutdown"


def test_run_once_verbose_includes_scheduler_transition(tmp_path: Path, capsys) -> None:
    path = tmp_path / "watchlist.json"
    assert main(["--watchlist", str(path), "watchlist", "add", "00700.HK"]) == 0
    capsys.readouterr()
    assert main(["--watchlist", str(path), "run", "--once", "--verbose"]) == 0
    out = capsys.readouterr().out
    assert "Scheduler: COLD -> COLD" in out
    assert "market_timestamp" in out
    assert "received_timestamp" in out

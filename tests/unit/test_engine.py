import json
from pathlib import Path

from market_sentinel.clock import FakeClock
from market_sentinel.domain.enums import FeedStatus, SchedulerLevel
from market_sentinel.health.feed_health import FeedHealthTracker
from market_sentinel.market_data.buffers import SymbolBuffers
from market_sentinel.market_data.state import MarketStateStore
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.runtime.engine import MarketEngine
from market_sentinel.scheduler.scheduler import AdaptiveScheduler
from market_sentinel.watchlist.watchlist import Watchlist


def _engine(
    tmp_path: Path, clock: FakeClock | None = None
) -> tuple[FakeClock, FakeProvider, MarketEngine]:
    clock = clock or FakeClock(wall=1_700_000_000.0, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    provider = FakeProvider(clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    return clock, provider, engine


async def test_tick_fetches_enabled_symbols_and_updates_state(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    engine.watchlist.add("600519.SH")
    engine.watchlist.disable("600519.SH")
    provider.set_quote(
        "00700.HK",
        price=602.5,
        prev_close=595.0,
        market_timestamp=clock.wall_time() - 0.2,
    )
    await engine.tick()
    assert provider.last_requested == ["00700.HK"]
    latest = engine.buffers.latest("00700.HK")
    assert latest is not None
    assert latest.price == 602.5
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.feed_status is FeedStatus.LIVE
    assert state.level is SchedulerLevel.COLD
    assert engine.buffers.latest("600519.SH") is None
    assert clock.monotonic_time() == 0.0


async def test_older_quote_is_suppressed(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("600519.SH")
    provider.set_quote("600519.SH", price=100.0, market_timestamp=50.0, volume=10.0)
    await engine.tick()
    first = engine.buffers.latest("600519.SH")
    assert first is not None
    clock.advance(10.0)
    provider.set_quote("600519.SH", price=90.0, market_timestamp=40.0, volume=11.0)
    result = await engine.tick()
    latest = engine.buffers.latest("600519.SH")
    assert latest is not None
    assert latest.price == 100.0
    assert latest.market_timestamp == 50.0
    assert engine.diagnostics.out_of_order_count == 1
    row = result.for_symbol("600519.SH")
    assert row is not None
    assert row.accepted_events == ()


async def test_duplicate_timestamp_replaces_without_second_buffer_row(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("600519.SH")
    provider.set_quote("600519.SH", price=100.0, market_timestamp=50.0)
    await engine.tick()
    clock.advance(10.0)
    provider.set_quote("600519.SH", price=101.0, market_timestamp=50.0)
    await engine.tick()
    buffer = engine.buffers.buffer("600519.SH")
    assert buffer is not None
    assert len(buffer.since(0.0)) == 1
    latest = engine.buffers.latest("600519.SH")
    assert latest is not None
    assert latest.price == 101.0
    assert engine.diagnostics.duplicate_timestamp_count == 1


async def test_timeout_does_not_reprocess_stale_buffer(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("600519.SH")
    provider.set_quote("600519.SH", price=100.0, market_timestamp=clock.wall_time() - 0.2)
    first = await engine.tick()
    assert first.for_symbol("600519.SH") is not None
    clock.advance(10.0)
    provider.set_timeout(True)
    second = await engine.tick()
    row = second.for_symbol("600519.SH")
    assert row is not None
    assert row.accepted_events == ()
    assert row.alert_candidates == ()
    assert engine.diagnostics.last_fetch_error == "TimeoutError"


async def test_missing_quote_does_not_reuse_previous_vendor_tick(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("600519.SH")
    provider.set_quote("600519.SH", price=100.0, market_timestamp=clock.wall_time() - 0.2)
    await engine.tick()
    clock.advance(10.0)
    provider.fail_symbol("600519.SH")
    result = await engine.tick()
    row = result.for_symbol("600519.SH")
    assert row is not None
    assert row.accepted_events == ()
    latest = engine.buffers.latest("600519.SH")
    assert latest is not None
    assert latest.price == 100.0


async def test_tick_timeout_is_not_disconnected(tmp_path: Path) -> None:
    _, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    provider.set_timeout(True)
    await engine.tick()
    state = engine.states.get("00700.HK")
    assert state is not None
    assert state.feed_status is not FeedStatus.DISCONNECTED


async def test_second_tick_waits_for_interval(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    await engine.tick()
    assert engine.scheduler.next_wait_s(["00700.HK"]) == 10.0
    provider.last_requested = []
    await engine.tick()
    assert provider.last_requested == []
    clock.advance_monotonic(10.0)
    await engine.tick()
    assert provider.last_requested == ["00700.HK"]


async def test_older_quote_does_not_refresh_feed_success(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("600519.SH")
    fresh_ts = clock.wall_time() - 0.2
    provider.set_quote("600519.SH", price=100.0, market_timestamp=fresh_ts, volume=10.0)
    await engine.tick()
    assert engine.health.status("600519.SH") is FeedStatus.LIVE
    result = None
    for _ in range(3):
        clock.advance(10.0)
        provider.set_quote("600519.SH", price=90.0, market_timestamp=fresh_ts - 10.0, volume=11.0)
        result = await engine.tick()
        row = result.for_symbol("600519.SH")
        assert row is not None
        assert row.accepted_events == ()
        assert row.alert_candidates == ()
        latest = engine.buffers.latest("600519.SH")
        assert latest is not None
        assert latest.price == 100.0
        assert latest.market_timestamp == fresh_ts
        state = engine.states.get("600519.SH")
        assert state is not None
        assert state.latest is not None
        assert state.latest.price == 100.0
    assert result is not None
    assert engine.diagnostics.out_of_order_count == 3
    assert engine.health.status("600519.SH") is FeedStatus.DISCONNECTED


async def test_duplicate_timestamp_does_not_repeat_alert_edge(tmp_path: Path) -> None:
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("00700.HK")
    baseline = clock.wall_time()
    provider.set_quote(
        "00700.HK",
        price=100.0,
        open=100.0,
        high=100.0,
        low=100.0,
        prev_close=100.0,
        volume=1000.0,
        market_timestamp=baseline,
    )
    await engine.tick()
    clock.advance(60.0)
    move_ts = clock.wall_time()
    provider.set_quote(
        "00700.HK",
        price=100.8,
        open=100.0,
        high=100.8,
        low=100.0,
        prev_close=100.0,
        volume=1100.0,
        market_timestamp=move_ts,
    )
    first = await engine.tick()
    row1 = first.for_symbol("00700.HK")
    assert row1 is not None
    assert row1.alert_candidates
    clock.advance(10.0)
    provider.set_quote(
        "00700.HK",
        price=100.8,
        open=100.0,
        high=100.8,
        low=100.0,
        prev_close=100.0,
        volume=1100.0,
        market_timestamp=move_ts,
    )
    second = await engine.tick()
    row2 = second.for_symbol("00700.HK")
    assert row2 is not None
    assert engine.diagnostics.duplicate_timestamp_count == 1
    assert row2.alert_candidates == ()
    latest = engine.buffers.latest("00700.HK")
    assert latest is not None
    assert latest.market_timestamp == move_ts
    assert latest.price == 100.8


async def test_replay_eof_does_not_treat_exhaustion_as_missing_quote(
    tmp_path: Path, caplog
) -> None:
    from market_sentinel.ipc.mapping import map_engine_state
    from market_sentinel.providers.replay import ReplayProvider

    caplog.set_level("WARNING")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "replay_quotes.jsonl"
    clock = FakeClock(wall=1_700_000_200.0, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add("000001.SZ")
    provider = ReplayProvider(fixture, clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    await engine.tick()
    clock.advance_monotonic(10.0)
    await engine.tick()
    live = engine.states.get("000001.SZ")
    assert live is not None
    assert live.latest is not None
    price = live.latest.price
    level = live.level
    clock.advance_monotonic(30.0)
    await engine.tick()
    after = engine.states.get("000001.SZ")
    assert after is not None
    assert after.latest is not None
    assert after.latest.price == price
    assert after.level is level
    assert engine.health.status("000001.SZ") is not FeedStatus.STALE
    assert engine.health.status("000001.SZ") is not FeedStatus.DISCONNECTED
    assert "missing quote" not in caplog.text
    wire = map_engine_state(engine).to_wire()
    assert wire.get("replay_complete") is True


async def test_live_missing_quote_still_observes_provider_error(tmp_path: Path, caplog) -> None:
    caplog.set_level("WARNING")
    clock, provider, engine = _engine(tmp_path)
    engine.watchlist.add("600519.SH")
    provider.set_quote("600519.SH", price=100.0, market_timestamp=clock.wall_time() - 0.2)
    await engine.tick()
    clock.advance(10.0)
    provider.fail_symbol("600519.SH")
    await engine.tick()
    assert "missing quote" in caplog.text
    assert engine.health.status("600519.SH") is not FeedStatus.DISCONNECTED


async def test_replay_final_batch_wrong_symbol_is_missing_quote_not_graceful_eof(
    tmp_path: Path, caplog
) -> None:
    from market_sentinel.ipc.mapping import map_engine_state
    from market_sentinel.providers.replay import ReplayProvider

    caplog.set_level("WARNING")
    fixture = tmp_path / "replay.jsonl"
    fixture.write_text(
        json.dumps(
            [
                {
                    "symbol": "AAA.SH",
                    "price": 10.0,
                    "open": 10.0,
                    "high": 10.0,
                    "low": 10.0,
                    "prev_close": 10.0,
                    "volume": 100.0,
                    "market_timestamp": 1_700_000_010.0,
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    clock = FakeClock(wall=1_700_000_200.0, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add("BBB.SH")
    provider = ReplayProvider(fixture, clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    await engine.tick()
    assert provider.source_exhausted() is True
    assert "missing quote" in caplog.text
    first_wire = map_engine_state(engine).to_wire()
    assert first_wire.get("replay_complete") is True
    caplog.clear()
    clock.advance_monotonic(10.0)
    await engine.tick()
    assert "missing quote" not in caplog.text
    assert engine.health.status("BBB.SH") is not FeedStatus.LIVE


async def test_replay_failure_before_eof_ages_to_stale(tmp_path: Path, caplog) -> None:
    from market_sentinel.providers.replay import ReplayProvider

    caplog.set_level("WARNING")
    fixture = tmp_path / "replay.jsonl"
    batch_ok = {
        "symbol": "BBB.SH",
        "price": 10.0,
        "open": 10.0,
        "high": 10.0,
        "low": 10.0,
        "prev_close": 10.0,
        "volume": 100.0,
        "market_timestamp": 1_700_000_010.0,
    }
    batch_other = {
        **batch_ok,
        "symbol": "AAA.SH",
        "market_timestamp": 1_700_000_010.1,
    }
    fixture.write_text(
        json.dumps([batch_ok]) + "\n" + json.dumps([batch_other]) + "\n",
        encoding="utf-8",
    )
    clock = FakeClock(wall=1_700_000_010.2, monotonic=0.0)
    watchlist = Watchlist(tmp_path / "watchlist.json")
    watchlist.add("BBB.SH")
    provider = ReplayProvider(fixture, clock)
    engine = MarketEngine(
        clock=clock,
        watchlist=watchlist,
        provider=provider,
        scheduler=AdaptiveScheduler(clock),
        buffers=SymbolBuffers(),
        states=MarketStateStore(),
        health=FeedHealthTracker(clock),
    )
    await engine.tick()
    assert engine.health.status("BBB.SH") is FeedStatus.LIVE
    clock.advance_monotonic(10.0)
    await engine.tick()
    assert provider.source_exhausted() is True
    assert "missing quote" in caplog.text
    assert engine.health.consecutive_failures("BBB.SH") == 1
    age_after_failure = engine.health.last_update_age("BBB.SH")
    assert age_after_failure == 10.0
    caplog.clear()
    clock.advance_monotonic(10.0)
    await engine.tick()
    assert "missing quote" not in caplog.text
    assert "provider error" not in caplog.text
    assert engine.health.consecutive_failures("BBB.SH") == 1
    assert engine.health.last_update_age("BBB.SH") == 20.0
    clock.advance_monotonic(10.0)
    await engine.tick()
    assert engine.health.last_update_age("BBB.SH") == 30.0
    assert engine.health.status("BBB.SH") is FeedStatus.STALE

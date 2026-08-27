from __future__ import annotations

from types import SimpleNamespace

from tools.live_probe.session_smoke import (
    PRIMARY_SYMBOLS,
    TEN_SYMBOL_BATCH,
    BatchSample,
    TickSample,
    evaluate_session,
    evaluate_volume_series,
    run_session_smoke,
)

from market_sentinel.clock import FakeClock
from market_sentinel.health.policy import HealthPolicy
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider


def test_health_policy_thresholds_are_unchanged() -> None:
    policy = HealthPolicy()
    assert policy.delayed_s == 3.0
    assert policy.stale_s == 30.0
    assert policy.disconnect_s == 60.0
    assert policy.disconnect_failures == 3


def test_volume_series_requires_positive_delta() -> None:
    stamps = [1.0, 2.0, 3.0]
    assert evaluate_volume_series(stamps, [10.0, 10.0, 10.0])
    assert not evaluate_volume_series(stamps, [10.0, 11.0, 11.0])
    assert any("decreased" in item for item in evaluate_volume_series(stamps, [10.0, 9.0, 9.0]))


def _tick(
    symbol: str,
    *,
    volume: float,
    market_ts: float,
    received_ts: float,
    feed_status: str = "LIVE",
) -> TickSample:
    return TickSample(
        symbol=symbol,
        price=10.0,
        volume=volume,
        high=11.0,
        low=9.0,
        turnover=None,
        market_timestamp=market_ts,
        received_timestamp=received_ts,
        latency_s=max(0.0, received_ts - market_ts),
        feed_status=feed_status,
        accepted_events=0,
        alert_candidates=0,
        context_create_count=1,
    )


def test_evaluate_session_accepts_truthful_delayed() -> None:
    ticks = [
        _tick("600519.SH", volume=10.0, market_ts=1.0, received_ts=10.0, feed_status="DELAYED"),
        _tick("600519.SH", volume=12.0, market_ts=2.0, received_ts=11.0, feed_status="DELAYED"),
        _tick("000001.SZ", volume=20.0, market_ts=1.0, received_ts=10.0, feed_status="DELAYED"),
        _tick("000001.SZ", volume=20.0, market_ts=2.0, received_ts=11.0, feed_status="DELAYED"),
    ]
    batches = [
        BatchSample(1, ("600519.SH",), ("600519.SH",), 1, True),
        BatchSample(2, PRIMARY_SYMBOLS, PRIMARY_SYMBOLS, 1, True),
        BatchSample(10, TEN_SYMBOL_BATCH, TEN_SYMBOL_BATCH, 1, True),
    ]
    report = evaluate_session(
        ticks,
        batches,
        expected_primary=PRIMARY_SYMBOLS,
        context_create_count=1,
        out_of_order_count=0,
    )
    assert report.passed, report.failures
    assert "DELAYED" in report.feed_statuses


def test_evaluate_session_rejects_live_when_latency_exceeds_delayed_s() -> None:
    ticks = [
        _tick("600519.SH", volume=10.0, market_ts=1.0, received_ts=10.0, feed_status="LIVE"),
        _tick("600519.SH", volume=12.0, market_ts=2.0, received_ts=11.0, feed_status="LIVE"),
        _tick("000001.SZ", volume=20.0, market_ts=1.0, received_ts=10.0, feed_status="LIVE"),
        _tick("000001.SZ", volume=21.0, market_ts=2.0, received_ts=11.0, feed_status="LIVE"),
    ]
    batches = [
        BatchSample(1, ("600519.SH",), ("600519.SH",), 1, True),
        BatchSample(2, PRIMARY_SYMBOLS, PRIMARY_SYMBOLS, 1, True),
        BatchSample(10, TEN_SYMBOL_BATCH, TEN_SYMBOL_BATCH, 1, True),
    ]
    report = evaluate_session(
        ticks,
        batches,
        expected_primary=PRIMARY_SYMBOLS,
        context_create_count=1,
        out_of_order_count=0,
    )
    assert not report.passed
    assert any("should be DELAYED" in item for item in report.failures)


def test_evaluate_session_rejects_all_zero_volume_deltas() -> None:
    ticks = [
        _tick("600519.SH", volume=10.0, market_ts=1.0, received_ts=1.2),
        _tick("600519.SH", volume=10.0, market_ts=1.0, received_ts=3.2),
        _tick("000001.SZ", volume=20.0, market_ts=1.0, received_ts=1.2),
        _tick("000001.SZ", volume=20.0, market_ts=1.0, received_ts=3.2),
    ]
    batches = [
        BatchSample(1, ("600519.SH",), ("600519.SH",), 1, True),
        BatchSample(2, PRIMARY_SYMBOLS, PRIMARY_SYMBOLS, 1, True),
        BatchSample(10, TEN_SYMBOL_BATCH, TEN_SYMBOL_BATCH, 1, True),
    ]
    report = evaluate_session(
        ticks,
        batches,
        expected_primary=PRIMARY_SYMBOLS,
        context_create_count=1,
        out_of_order_count=0,
    )
    assert not report.passed
    assert any("positive same-session volume" in item for item in report.failures)


def _quote(symbol: str, *, volume: float, ts: float) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        last_done=10.0,
        open=10.0,
        high=11.0,
        low=9.0,
        prev_close=10.0,
        volume=volume,
        turnover="1",
        timestamp=ts,
        trade_status=0,
    )


async def test_run_session_smoke_reuses_sdk_context_and_records_volume() -> None:
    clock = FakeClock(wall=1_700_000_050.0, monotonic=0.0)
    state = {"n": 0}

    class Ctx:
        async def quote(self, symbols: list[str]) -> list[SimpleNamespace]:
            state["n"] += 1
            volume = 1000.0 + state["n"]
            ts = clock.wall_time() - 0.2
            return [_quote(symbol, volume=volume, ts=ts) for symbol in symbols]

    def factory() -> Ctx:
        return Ctx()

    provider = LongbridgeQuoteProvider(clock, sdk_factory=factory)
    report = await run_session_smoke(
        clock=clock,
        provider=provider,
        samples=3,
        interval_s=2.0,
        sleep=_noop_sleep,
    )
    assert report.passed, report.failures
    assert report.context_create_count == 1
    assert {item.size for item in report.batches} == {1, 2, 10}
    assert report.positive_volume_deltas >= 1


async def _noop_sleep(_seconds: float) -> None:
    return None

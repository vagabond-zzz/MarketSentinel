from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from tools.live_probe.common import Observation
from tools.live_probe.live_gate import evaluate_quote, evaluate_series

CST = timezone(timedelta(hours=8))


def _obs(**overrides: object) -> Observation:
    stamp = datetime(2026, 8, 28, 11, 18, 6, tzinfo=CST)
    payload = dict(
        provider="tencent",
        symbol="600519.SH",
        vendor_symbol="sh600519",
        received_timestamp=stamp.timestamp() + 3.0,
        price=1294.4,
        open=1289.0,
        high=1296.1,
        low=1288.0,
        prev_close=1292.3,
        volume_raw=8200.0,
        turnover_raw=1.0e9,
        market_timestamp_raw="20260828111806",
        market_timestamp_parsed=stamp.timestamp(),
        trade_status=None,
        field_confidence={},
        received_minus_market_s=3.0,
        name="Moutai",
        field_count=88,
    )
    payload.update(overrides)
    return Observation(**payload)  # type: ignore[arg-type]


def test_evaluate_quote_accepts_in_session_row() -> None:
    obs = _obs()
    failures = evaluate_quote(
        obs, today=date(2026, 8, 28), min_fields=80, now=obs.received_timestamp
    )
    assert failures == []


def test_evaluate_quote_rejects_stale_date() -> None:
    failures = evaluate_quote(_obs(), today=date(2026, 8, 27), min_fields=80)
    assert any("quote date" in item for item in failures)


def test_evaluate_series_requires_freshness_evidence() -> None:
    first = _obs()
    idle = _obs(delta_volume=0.0)
    idle.market_timestamp_parsed = first.market_timestamp_parsed
    assert evaluate_series([first, idle])
    moved = _obs(volume_raw=8210.0, delta_volume=10.0)
    moved.market_timestamp_parsed = first.market_timestamp_parsed
    assert evaluate_series([first, moved]) == []

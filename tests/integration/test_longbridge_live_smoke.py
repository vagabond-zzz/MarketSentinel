from __future__ import annotations

import os

import pytest
from tools.live_probe.session_smoke import run_session_smoke

from market_sentinel.clock import SystemClock
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider, credentials_present

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_longbridge_live_ashare_quotes() -> None:
    if not credentials_present():
        pytest.skip("Longbridge credentials are not set")
    provider = LongbridgeQuoteProvider(SystemClock())
    snapshots = await provider.fetch_quotes(["600519.SH", "000001.SZ"])
    by_symbol = {item.symbol: item for item in snapshots}
    assert set(by_symbol) == {"600519.SH", "000001.SZ"}
    assert provider.diagnostics.context_create_count == 1
    for snapshot in snapshots:
        assert snapshot.price > 0
        assert snapshot.volume >= 0
        assert snapshot.turnover is None
        assert snapshot.market_timestamp != snapshot.received_timestamp
    again = await provider.fetch_quotes(["600519.SH", "000001.SZ"])
    assert len(again) == 2
    assert provider.diagnostics.context_create_count == 1


@pytest.mark.asyncio
async def test_longbridge_live_session_smoke() -> None:
    if not credentials_present():
        pytest.skip("Longbridge credentials are not set")
    samples = int(os.environ.get("MARKET_SENTINEL_LIVE_SAMPLES", "20"))
    interval = float(os.environ.get("MARKET_SENTINEL_LIVE_INTERVAL", "2"))
    report = await run_session_smoke(samples=samples, interval_s=interval)
    assert report.passed, "\n".join(report.failures)

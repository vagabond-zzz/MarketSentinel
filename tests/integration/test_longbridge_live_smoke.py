from __future__ import annotations

import pytest

from market_sentinel.clock import SystemClock
from market_sentinel.errors import ProviderError
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider, credentials_present

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_longbridge_live_ashare_quotes() -> None:
    if not credentials_present():
        pytest.skip("Longbridge credentials are not set")
    provider = LongbridgeQuoteProvider(SystemClock())
    try:
        snapshots = await provider.fetch_quotes(["600519.SH", "000001.SZ"])
    except ProviderError as exc:
        pytest.skip(str(exc))
    except TimeoutError as exc:
        pytest.skip(str(exc))
    by_symbol = {item.symbol: item for item in snapshots}
    assert set(by_symbol) == {"600519.SH", "000001.SZ"}
    for snapshot in snapshots:
        assert snapshot.price > 0
        assert snapshot.volume >= 0
        assert snapshot.turnover is None
        assert snapshot.market_timestamp != snapshot.received_timestamp

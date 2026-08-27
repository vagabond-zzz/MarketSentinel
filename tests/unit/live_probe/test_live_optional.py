from __future__ import annotations

import pytest
from tools.live_probe.common import ProbeTransportError
from tools.live_probe.longbridge_probe import credentials_present
from tools.live_probe.tencent_probe import fetch_tencent_quotes


@pytest.mark.live
def test_tencent_live_fetch_optional() -> None:
    try:
        rows = fetch_tencent_quotes(["600519.SH", "000001.SZ"])
    except ProbeTransportError as exc:
        pytest.skip(str(exc))
    assert {row.symbol for row in rows} == {"600519.SH", "000001.SZ"}
    assert all(row.price and row.price > 0 for row in rows)


@pytest.mark.live
def test_longbridge_live_requires_credentials() -> None:
    if not credentials_present():
        pytest.skip("Longbridge credentials are not set")
    pytest.skip("live SDK call is invoked only via tools.live_probe.longbridge_probe")

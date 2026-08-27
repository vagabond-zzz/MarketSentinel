from __future__ import annotations

import pytest
from tools.live_probe.common import (
    MIN_INTERVAL_S,
    ProbeTransportError,
    attach_deltas,
    clamp_interval,
    high_low_plausible,
)
from tools.live_probe.tencent_probe import fetch_tencent_quotes


def test_refuses_sub_two_second_interval() -> None:
    with pytest.raises(ValueError, match="interval"):
        clamp_interval(0.1)
    assert clamp_interval(2.0) == 2.0
    assert clamp_interval(5.0) == 5.0
    assert MIN_INTERVAL_S == 2.0


def test_attach_deltas_does_not_convert_units() -> None:
    from tools.live_probe.common import Observation

    first = Observation(
        provider="tencent",
        symbol="600519.SH",
        vendor_symbol="sh600519",
        received_timestamp=10.0,
        price=10.0,
        open=10.0,
        high=11.0,
        low=9.0,
        prev_close=10.0,
        volume_raw=100.0,
        turnover_raw=1000.0,
        market_timestamp_raw="a",
        market_timestamp_parsed=9.0,
        trade_status=None,
        field_confidence={},
        received_minus_market_s=1.0,
    )
    second = Observation(
        provider="tencent",
        symbol="600519.SH",
        vendor_symbol="sh600519",
        received_timestamp=12.0,
        price=10.0,
        open=10.0,
        high=11.0,
        low=9.0,
        prev_close=10.0,
        volume_raw=130.0,
        turnover_raw=1300.0,
        market_timestamp_raw="b",
        market_timestamp_parsed=11.0,
        trade_status=None,
        field_confidence={},
        received_minus_market_s=1.0,
    )
    out = attach_deltas([first, second])
    assert out[0].delta_volume is None
    assert out[1].delta_volume == 30.0
    assert out[1].delta_turnover == 300.0
    assert out[1].turnover_div_volume == pytest.approx(10.0)
    assert out[1].turnover_div_volume_div_price == pytest.approx(1.0)
    assert out[1].turnover_div_volume_div_100 == pytest.approx(0.1)
    assert out[1].turnover_div_volume_times_100 == pytest.approx(1000.0)


def test_high_low_plausible_does_not_claim_session_extremes() -> None:
    ok, note = high_low_plausible(price=10.0, open_=10.5, high=11.0, low=9.0)
    assert ok is True
    assert "LIKELY" in note
    bad, _ = high_low_plausible(price=10.0, open_=10.0, high=0.0, low=0.0)
    assert bad is False


def test_http_error_and_timeout_fail_closed() -> None:
    def boom(_url: str, _timeout: float) -> str:
        raise TimeoutError("timed out")

    with pytest.raises(ProbeTransportError, match="timeout"):
        fetch_tencent_quotes(["600519.SH"], transport=boom, timeout_s=1.0)

    def not_found(_url: str, _timeout: float) -> str:
        raise ProbeTransportError("HTTP 500")

    with pytest.raises(ProbeTransportError, match="HTTP"):
        fetch_tencent_quotes(["600519.SH"], transport=not_found, timeout_s=1.0)

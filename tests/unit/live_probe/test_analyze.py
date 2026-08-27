from __future__ import annotations

from tools.live_probe.analyze import (
    classify_high_low,
    classify_timestamp,
    classify_turnover,
    classify_volume,
    classify_volume_unit,
    summarize,
)
from tools.live_probe.common import Observation


def _obs(**fields: object) -> Observation:
    base = {
        "provider": "tencent",
        "symbol": "600519.SH",
        "vendor_symbol": "sh600519",
        "received_timestamp": 1000.0,
        "price": 10.0,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "prev_close": 10.0,
        "volume_raw": 100.0,
        "turnover_raw": 1000.0,
        "market_timestamp_raw": "t",
        "market_timestamp_parsed": 990.0,
        "trade_status": None,
        "field_confidence": {},
        "delta_volume": None,
        "delta_turnover": None,
        "turnover_div_volume": None,
        "turnover_div_volume_div_price": None,
        "turnover_div_volume_div_100": None,
        "turnover_div_volume_times_100": None,
        "received_minus_market_s": 10.0,
        "error": None,
    }
    base.update(fields)
    return Observation(**base)  # type: ignore[arg-type]


def test_volume_confirmed_cumulative_when_nondecreasing_and_increases() -> None:
    series = [
        _obs(volume_raw=100.0, delta_volume=None),
        _obs(volume_raw=110.0, delta_volume=10.0),
        _obs(volume_raw=110.0, delta_volume=0.0),
        _obs(volume_raw=125.0, delta_volume=15.0),
    ]
    result = classify_volume(series)
    assert result.label == "CONFIRMED_CUMULATIVE"


def test_volume_not_cumulative_on_decrease() -> None:
    series = [
        _obs(volume_raw=100.0, delta_volume=None),
        _obs(volume_raw=90.0, delta_volume=-10.0),
    ]
    assert classify_volume(series).label == "NOT_CUMULATIVE"


def test_volume_unknown_with_single_sample() -> None:
    assert classify_volume([_obs()]).label == "UNKNOWN"


def test_volume_likely_when_flat() -> None:
    series = [
        _obs(volume_raw=100.0, delta_volume=None),
        _obs(volume_raw=100.0, delta_volume=0.0),
        _obs(volume_raw=100.0, delta_volume=0.0),
    ]
    assert classify_volume(series).label == "LIKELY_CUMULATIVE"


def test_turnover_commensurate_when_ratio_near_price() -> None:
    # turnover/volume ≈ price
    series = [
        _obs(price=10.0, volume_raw=100.0, turnover_raw=1000.0, turnover_div_volume=10.0),
        _obs(price=10.0, volume_raw=110.0, turnover_raw=1100.0, turnover_div_volume=10.0),
    ]
    assert classify_turnover(series).label == "COMMENSURATE_WITH_VOLUME"


def test_turnover_mismatch_when_ratio_is_price_times_100() -> None:
    series = [
        _obs(price=10.0, volume_raw=100.0, turnover_raw=100000.0, turnover_div_volume=1000.0),
        _obs(price=10.0, volume_raw=110.0, turnover_raw=110000.0, turnover_div_volume=1000.0),
    ]
    result = classify_turnover(series)
    assert result.label == "UNIT_MISMATCH_LIKELY"


def test_volume_unit_lot_inferred_when_ratio_near_price_times_100() -> None:
    result = classify_volume_unit(
        price=1292.30,
        volume_raw=24767.0,
        turnover_raw=3203715661.0,
    )
    assert result.label == "手"
    assert result.confidence == "INFERRED"


def test_timestamp_invalid_when_missing() -> None:
    series = [_obs(market_timestamp_parsed=None, received_minus_market_s=None)]
    assert classify_timestamp(series).label == "INVALID_AS_MARKET_TIME"


def test_timestamp_valid_when_parsed_and_not_receive_clock() -> None:
    series = [
        _obs(
            market_timestamp_parsed=100.0, received_timestamp=1000.0, received_minus_market_s=900.0
        ),
        _obs(
            market_timestamp_parsed=101.0, received_timestamp=1002.0, received_minus_market_s=901.0
        ),
    ]
    assert classify_timestamp(series).label == "VALID_MARKET_TIME"


def test_high_low_likely_when_consistent_but_undocumented() -> None:
    series = [_obs(price=10.0, open=10.5, high=11.0, low=9.0)]
    result = classify_high_low(series)
    assert result.label == "LIKELY"
    assert result.confidence == "INFERRED"


def test_summarize_groups_by_provider_and_symbol() -> None:
    series = [
        _obs(volume_raw=100.0, delta_volume=None),
        _obs(volume_raw=100.0, delta_volume=0.0),
    ]
    report = summarize(series)
    assert "tencent:600519.SH" in report
    assert report["tencent:600519.SH"]["volume"]["label"] == "LIKELY_CUMULATIVE"

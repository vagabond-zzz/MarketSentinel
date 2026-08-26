from dataclasses import replace

from market_sentinel.domain.features import MarketFeatures

DETECTED_AT = 1_700_000_100.0


def make_features(**overrides: object) -> MarketFeatures:
    base = MarketFeatures(
        symbol="00700.HK",
        market_timestamp=1_700_000_060.0,
        received_timestamp=1_700_000_061.0,
        change_1m=None,
        change_5m=None,
        change_15m=None,
        change_day=None,
        day_range_position=None,
        volume_1m=None,
        volume_5m=None,
        volume_ratio_1m=None,
        volume_ratio_5m=None,
        vwap=None,
        above_vwap=None,
        ema5=None,
        ema20=None,
        rsi14=None,
        session_high_ref=100.0,
        session_low_ref=100.0,
        session_high_obs=100.0,
        session_low_obs=100.0,
    )
    return replace(base, **overrides)

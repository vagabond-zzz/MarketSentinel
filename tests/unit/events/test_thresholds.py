from market_sentinel.events.thresholds import (
    RAPID_1M_SEV2,
    RAPID_1M_SEV3,
    RAPID_1M_SEV4,
    RAPID_5M_SEV3,
    RAPID_5M_SEV4,
    RAPID_5M_SEV5,
)


def test_frozen_thresholds_are_decimal_fractions_not_percent_points() -> None:
    assert RAPID_1M_SEV2 == 0.006
    assert RAPID_1M_SEV3 == 0.010
    assert RAPID_5M_SEV3 == 0.012
    assert RAPID_1M_SEV4 == 0.015
    assert RAPID_5M_SEV4 == 0.020
    assert RAPID_5M_SEV5 == 0.035
    assert RAPID_1M_SEV2 != 0.6

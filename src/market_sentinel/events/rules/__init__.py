from market_sentinel.events.rules.day_high_breakout import DayHighBreakoutRule
from market_sentinel.events.rules.day_low_breakdown import DayLowBreakdownRule
from market_sentinel.events.rules.price_volume_expansion import PriceVolumeExpansionRule
from market_sentinel.events.rules.rapid_move import RapidMoveRule
from market_sentinel.events.rules.volume_spike import VolumeSpikeRule
from market_sentinel.events.rules.vwap_cross import VwapCrossRule

__all__ = [
    "DayHighBreakoutRule",
    "DayLowBreakdownRule",
    "PriceVolumeExpansionRule",
    "RapidMoveRule",
    "VolumeSpikeRule",
    "VwapCrossRule",
]


def default_rules() -> tuple[
    RapidMoveRule,
    VolumeSpikeRule,
    PriceVolumeExpansionRule,
    DayHighBreakoutRule,
    DayLowBreakdownRule,
    VwapCrossRule,
]:
    return (
        RapidMoveRule(),
        VolumeSpikeRule(),
        PriceVolumeExpansionRule(),
        DayHighBreakoutRule(),
        DayLowBreakdownRule(),
        VwapCrossRule(),
    )

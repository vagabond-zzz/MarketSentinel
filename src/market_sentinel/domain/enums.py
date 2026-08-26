from enum import StrEnum


class SchedulerLevel(StrEnum):
    COLD = "COLD"
    WARM = "WARM"
    HOT = "HOT"


class FeedStatus(StrEnum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"


class EventType(StrEnum):
    RAPID_MOVE = "rapid_move"
    VOLUME_SPIKE = "volume_spike"
    PRICE_VOLUME_EXPANSION = "price_volume_expansion"
    DAY_HIGH_BREAKOUT = "day_high_breakout"
    DAY_LOW_BREAKDOWN = "day_low_breakdown"
    VWAP_CROSS = "vwap_cross"


class EventDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


class SignalPriority(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    IMPORTANT = "important"
    CRITICAL = "critical"


class GeneratedBy(StrEnum):
    RULE = "rule"

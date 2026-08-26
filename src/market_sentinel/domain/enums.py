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

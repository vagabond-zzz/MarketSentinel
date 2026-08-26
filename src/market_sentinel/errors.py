class MarketSentinelError(Exception):
    """Base error for Market Sentinel core."""


class SnapshotValidationError(MarketSentinelError):
    """Raised when a raw quote cannot be turned into a MarketSnapshot."""

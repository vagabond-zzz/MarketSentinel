class MarketSentinelError(Exception):
    """Base error for Market Sentinel core."""


class SnapshotValidationError(MarketSentinelError):
    """Raised when a raw quote cannot be turned into a MarketSnapshot."""


class WatchlistFullError(MarketSentinelError):
    """Raised when adding would exceed the watchlist limit."""


class WatchlistSymbolError(MarketSentinelError):
    """Raised when a watchlist symbol is missing."""

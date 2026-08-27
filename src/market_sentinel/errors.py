class MarketSentinelError(Exception):
    """Base error for Market Sentinel core."""


class SnapshotValidationError(MarketSentinelError):
    """Raised when a raw quote cannot be turned into a MarketSnapshot."""


class WatchlistFullError(MarketSentinelError):
    """Raised when adding would exceed the watchlist limit."""


class WatchlistSymbolError(MarketSentinelError):
    """Raised when a watchlist symbol is missing."""


class InvalidSchedulerLevelError(MarketSentinelError):
    """Raised when a scheduler level is not a known enum value."""


class ProviderError(MarketSentinelError):
    """Provider transport or mapping failed. No snapshot is produced."""


class ProviderAuthError(ProviderError):
    """Credentials missing or rejected. Values must never appear in the message."""


class ProviderRateLimitError(ProviderError):
    """Vendor refused the request because of rate limiting."""


class ProviderUnavailableError(ProviderError):
    """SDK missing, server error, or other unavailable condition."""

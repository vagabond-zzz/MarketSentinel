from __future__ import annotations

from market_sentinel.errors import MarketSentinelError


class IntelligenceError(MarketSentinelError):
    """Intelligence sidecar failed. Rule Signal must still be kept."""


class IntelligenceTimeoutError(IntelligenceError):
    """Model request exceeded the configured timeout."""


class IntelligenceTransportError(IntelligenceError):
    """Network or HTTP transport failed."""


class IntelligenceUnavailableError(IntelligenceError):
    """Provider or model is unavailable."""


class IntelligenceRateLimitError(IntelligenceError):
    """Provider refused the request because of rate limiting."""


class IntelligenceMalformedError(IntelligenceError):
    """Model output could not be parsed as the required JSON object."""


class IntelligenceAuthError(IntelligenceError):
    """API key missing or rejected. The secret must never appear in the message."""

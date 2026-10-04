"""Read-only capability facade (Core → Capabilities → CLI / future MCP)."""

from market_sentinel.capabilities.api import MarketCapabilities
from market_sentinel.capabilities.errors import (
    CapabilityError,
    CapabilityErrorCode,
    map_exception,
)
from market_sentinel.capabilities.views import (
    EventView,
    FeedHealthReport,
    RecentEventsBuffer,
    SymbolFeedHealth,
)

__all__ = [
    "CapabilityError",
    "CapabilityErrorCode",
    "EventView",
    "FeedHealthReport",
    "MarketCapabilities",
    "RecentEventsBuffer",
    "SymbolFeedHealth",
    "map_exception",
]

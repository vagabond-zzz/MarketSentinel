from __future__ import annotations

from pathlib import Path

from market_sentinel.clock import Clock
from market_sentinel.providers.base import MarketProvider
from market_sentinel.providers.fake import FakeProvider
from market_sentinel.providers.longbridge import LongbridgeQuoteProvider, QuoteClient
from market_sentinel.providers.replay import ReplayProvider

HTTP_STUB_MESSAGE = "HttpQuoteProvider is not implemented; use fake, replay, or longbridge."


def create_provider(
    name: str,
    clock: Clock,
    *,
    replay_path: Path | None = None,
    quote_client: QuoteClient | None = None,
) -> MarketProvider:
    if name == "fake":
        return FakeProvider(clock)
    if name == "replay":
        if replay_path is None:
            raise ValueError("--replay path is required for replay provider")
        return ReplayProvider(replay_path, clock)
    if name == "http":
        raise ValueError(HTTP_STUB_MESSAGE)
    if name == "longbridge":
        return LongbridgeQuoteProvider(clock, quote_client=quote_client)
    raise ValueError(f"unknown provider: {name}")

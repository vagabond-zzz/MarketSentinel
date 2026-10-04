"""Stable, machine-mappable error semantics for the capabilities layer.

Host layers (CLI today, the future MCP server) must map failures by error
code, never by parsing exception strings.
"""

from __future__ import annotations

from enum import StrEnum

from market_sentinel.errors import MarketSentinelError


class CapabilityErrorCode(StrEnum):
    NOT_FOUND = "not_found"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_RUNNING = "not_running"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INTERNAL = "internal"


class CapabilityError(MarketSentinelError):
    """Capability failure carrying a stable code.

    Messages are safe for host display: they never include credentials,
    filesystem paths, or internal object state.
    """

    def __init__(self, code: CapabilityErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def map_exception(exc: BaseException) -> CapabilityError:
    """Map an unexpected exception onto a stable capability error code.

    Capability methods are synchronous in-memory reads, so this is a
    defensive boundary (e.g. a host-imposed timeout surfacing through
    asyncio.TimeoutError), not normal control flow.
    """
    if isinstance(exc, CapabilityError):
        return exc
    if isinstance(exc, TimeoutError):  # asyncio.TimeoutError is an alias on 3.12+
        return CapabilityError(CapabilityErrorCode.TIMEOUT, "capability execution timed out")
    if isinstance(exc, (KeyError, StopIteration)):
        return CapabilityError(CapabilityErrorCode.NOT_FOUND, "requested object was not found")
    if isinstance(exc, (TypeError, ValueError)):
        return CapabilityError(CapabilityErrorCode.INVALID_ARGUMENT, "invalid capability argument")
    return CapabilityError(CapabilityErrorCode.INTERNAL, "unexpected capability failure")

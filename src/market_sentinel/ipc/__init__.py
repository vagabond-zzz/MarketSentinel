"""JSONL IPC protocol v1.

Core models are mapped to wire DTOs; never serialize MarketState with asdict.

Host restart (TypeScript ProcessManager): on unexpected child exit, reject all
pending requests, mark disconnected, dispose old stream/process handlers, then
start a new process with hello → set_watchlist → start. Do not reuse a request
map across daemon instances.
"""

from market_sentinel.ipc.codec import decode_line, encode_message
from market_sentinel.ipc.dto import WireAlertCandidate, WireMarketState, WireSignal, WireSymbolState
from market_sentinel.ipc.protocol import PROTOCOL_VERSION, DaemonPhase

__all__ = [
    "PROTOCOL_VERSION",
    "DaemonPhase",
    "WireAlertCandidate",
    "WireMarketState",
    "WireSignal",
    "WireSymbolState",
    "decode_line",
    "encode_message",
]

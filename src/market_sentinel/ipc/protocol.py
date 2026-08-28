from enum import StrEnum

PROTOCOL_VERSION = 1

HOST_COMMANDS = frozenset(
    {
        "hello",
        "start",
        "pause",
        "resume",
        "set_watchlist",
        "get_state",
        "host_interaction",
        "shutdown",
    }
)


class DaemonPhase(StrEnum):
    AWAITING_HELLO = "AWAITING_HELLO"
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class ErrorCode(StrEnum):
    INVALID_JSON = "invalid_json"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    UNKNOWN_TYPE = "unknown_type"
    MISSING_REQUEST_ID = "missing_request_id"
    INVALID_PAYLOAD = "invalid_payload"
    NOT_READY = "not_ready"
    NOT_STARTED = "not_started"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    WATCHLIST_FULL = "watchlist_full"
    DUPLICATE_SYMBOL = "duplicate_symbol"

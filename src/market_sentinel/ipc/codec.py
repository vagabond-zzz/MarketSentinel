from __future__ import annotations

import json
from typing import Any

from market_sentinel.ipc.protocol import PROTOCOL_VERSION, ErrorCode


def encode_message(
    message_type: str,
    *,
    request_id: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"protocol_version": PROTOCOL_VERSION, "type": message_type}
    if request_id is not None:
        payload["request_id"] = request_id
    payload.update(fields)
    return payload


def encode_error(
    code: ErrorCode | str,
    message: str,
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    return encode_message(
        "error",
        request_id=request_id,
        code=str(code),
        message=message,
    )


def decode_line(line: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Parse one JSONL command.

    Returns ``(command, None)`` or ``(None, error_message)``.
    """
    stripped = line.strip()
    if not stripped:
        return None, None
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError:
        return None, encode_error(ErrorCode.INVALID_JSON, "line is not valid JSON")
    if not isinstance(raw, dict):
        return None, encode_error(ErrorCode.INVALID_JSON, "JSON line must be an object")
    version = raw.get("protocol_version")
    request_id = raw.get("request_id")
    if version != PROTOCOL_VERSION:
        return None, encode_error(
            ErrorCode.PROTOCOL_MISMATCH,
            f"unsupported protocol_version: {version!r}",
            request_id=request_id if isinstance(request_id, str) else None,
        )
    message_type = raw.get("type")
    if not isinstance(message_type, str) or not message_type:
        return None, encode_error(
            ErrorCode.INVALID_PAYLOAD,
            "type must be a non-empty string",
            request_id=request_id if isinstance(request_id, str) else None,
        )
    return raw, None

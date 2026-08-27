from market_sentinel.ipc.codec import decode_line, encode_message
from market_sentinel.ipc.protocol import PROTOCOL_VERSION


def test_decode_valid_command() -> None:
    command, error = decode_line('{"protocol_version":1,"type":"hello","request_id":"r1"}')
    assert error is None
    assert command is not None
    assert command["type"] == "hello"
    assert command["request_id"] == "r1"


def test_decode_invalid_json() -> None:
    command, error = decode_line("{not json")
    assert command is None
    assert error is not None
    assert error["type"] == "error"
    assert error["code"] == "invalid_json"
    assert error["protocol_version"] == PROTOCOL_VERSION


def test_decode_protocol_mismatch() -> None:
    command, error = decode_line('{"protocol_version":99,"type":"hello","request_id":"r1"}')
    assert command is None
    assert error is not None
    assert error["code"] == "protocol_mismatch"
    assert error["request_id"] == "r1"


def test_decode_unknown_type_is_left_to_daemon() -> None:
    command, error = decode_line('{"protocol_version":1,"type":"nope","request_id":"r1"}')
    assert error is None
    assert command is not None
    assert command["type"] == "nope"


def test_blank_line_is_ignored() -> None:
    command, error = decode_line("  \n")
    assert command is None
    assert error is None


def test_encode_message_includes_version() -> None:
    encoded = encode_message("ack", request_id="r1")
    assert encoded == {"protocol_version": 1, "type": "ack", "request_id": "r1"}

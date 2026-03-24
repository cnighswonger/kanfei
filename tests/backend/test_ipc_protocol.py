"""Tests for IPC wire protocol (JSON-over-newline)."""

from app.ipc.protocol import (
    encode_message,
    decode_message,
    CMD_STATUS,
    CMD_PROBE,
    CMD_CONNECT,
)


class TestEncodeMessage:

    def test_simple_dict(self):
        result = encode_message({"cmd": "status"})
        assert result.endswith(b"\n")
        assert b'"cmd":"status"' in result

    def test_nested_dict(self):
        msg = {"cmd": "write_config", "data": {"key": "value", "num": 42}}
        result = encode_message(msg)
        assert result.endswith(b"\n")
        assert b'"num":42' in result

    def test_none_value(self):
        result = encode_message({"key": None})
        assert b"null" in result

    def test_compact_separators(self):
        result = encode_message({"a": 1, "b": 2})
        # Compact separators: no spaces after , and :
        decoded = result.decode()
        assert ": " not in decoded
        assert ", " not in decoded


class TestDecodeMessage:

    def test_simple_message(self):
        raw = b'{"cmd":"status"}\n'
        result = decode_message(raw)
        assert result == {"cmd": "status"}

    def test_strips_whitespace(self):
        raw = b'  {"ok":true}  \n'
        result = decode_message(raw)
        assert result == {"ok": True}

    def test_nested_data(self):
        raw = b'{"ok":true,"data":{"temp":72}}\n'
        result = decode_message(raw)
        assert result["data"]["temp"] == 72


class TestRoundTrip:

    def test_status_command(self):
        msg = {"cmd": CMD_STATUS}
        assert decode_message(encode_message(msg)) == msg

    def test_probe_command(self):
        msg = {"cmd": CMD_PROBE}
        assert decode_message(encode_message(msg)) == msg

    def test_connect_with_params(self):
        msg = {"cmd": CMD_CONNECT, "port": "/dev/ttyUSB0", "baud": 19200}
        assert decode_message(encode_message(msg)) == msg

    def test_response_with_error(self):
        msg = {"ok": False, "error": "Connection refused"}
        assert decode_message(encode_message(msg)) == msg

    def test_complex_data(self):
        msg = {
            "ok": True,
            "data": {
                "sensors": {"temp": 72.5, "humidity": 45, "wind": None},
                "connected": True,
            },
        }
        assert decode_message(encode_message(msg)) == msg


class TestCommandConstants:

    def test_no_duplicates(self):
        from app.ipc import protocol
        cmds = [v for k, v in vars(protocol).items()
                if k.startswith("CMD_") and isinstance(v, str)]
        assert len(cmds) == len(set(cmds))

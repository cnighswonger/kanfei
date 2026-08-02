"""Tests for GETEE and RECEIVERS on Vantage stations (Ref #221).

The load-bearing case here is RECEIVERS returning an empty result.

On a Vantage Vue it genuinely reports 0x00 — no transmitters heard — while
the station is working perfectly: measured on fw 2.12, RECEIVERS gave 0x00
and EEPROM USETX gave 0x00 at the same moment RXCHECK reported 23,516
packets received and LOOP returned live sensor data. The Vue's suite is
integrated rather than paired as an addressable transmitter, so the Tx-ID
mechanism (a Vantage Pro2 concept) has nothing to report.

That makes [] a *correct answer*, and the tests below pin the distinction
between "no transmitters" and "no response" so a future change cannot
quietly turn a working Vue into an error state.
"""

import struct

import pytest

from app.protocol.crc import crc_calculate
from app.protocol.vantage.commands import cmd_getee, cmd_receivers
from app.protocol.vantage.constants import EEPROM_SIZE, GETEE_TOTAL_SIZE
from app.protocol.vantage.driver import VantageDriver


class TestCommandFormat:
    def test_receivers_command(self):
        assert cmd_receivers() == b"RECEIVERS\n"

    def test_getee_command(self):
        assert cmd_getee() == b"GETEE\n"


class TestSizeConstants:
    def test_eeprom_is_4k(self):
        assert EEPROM_SIZE == 4096

    def test_total_includes_crc(self):
        assert GETEE_TOTAL_SIZE == EEPROM_SIZE + 2


class _FakeSerial:
    """Minimal SerialPort stand-in that replays a scripted response."""

    def __init__(self, response: bytes, ack: int | None = None):
        self._response = response
        self._ack = ack
        self.is_open = True

    def flush(self):
        pass

    def send(self, data):
        pass

    def receive(self, n):
        out, self._response = self._response[:n], self._response[n:]
        return out

    def receive_byte(self):
        return self._ack


def _driver_with(response: bytes, ack: int | None = None) -> VantageDriver:
    drv = VantageDriver("/dev/null", 19200)
    drv.serial = _FakeSerial(response, ack)
    drv._wakeup = lambda: None      # bypass the console handshake
    return drv


class TestReceiversBitmask:
    """Bit N corresponds to Tx ID N+1 (manual §IX.1)."""

    @pytest.mark.parametrize("bitmask,expected", [
        (0x00, []),
        (0x01, [1]),
        (0x02, [2]),
        (0x03, [1, 2]),
        (0x05, [1, 3]),
        (0x80, [8]),
        (0xFF, [1, 2, 3, 4, 5, 6, 7, 8]),
    ])
    def test_bitmask_decodes_to_transmitter_ids(self, bitmask, expected):
        drv = _driver_with(b"\n\rOK\n\r" + bytes([bitmask]))
        assert drv.receivers() == expected

    def test_empty_is_a_valid_answer_not_a_failure(self):
        """A Vue reports 0x00 while working normally. [] must come back as
        a real result, distinguishable from None."""
        drv = _driver_with(b"\n\rOK\n\r\x00")
        result = drv.receivers()
        assert result == []
        assert result is not None

    def test_no_ok_in_response_is_none(self):
        drv = _driver_with(b"\n\rgarbage\n\r")
        assert drv.receivers() is None

    def test_missing_payload_byte_is_none(self):
        """OK arrived but the bitmask did not — that IS a failure, and must
        not be confused with a legitimate 0x00."""
        drv = _driver_with(b"\n\rOK\n\r")
        assert drv.receivers() is None

    def test_empty_result_distinguishable_from_no_response(self):
        """The whole point: these two cases must not collapse together."""
        working_vue = _driver_with(b"\n\rOK\n\r\x00")
        no_answer = _driver_with(b"")
        assert working_vue.receivers() == []
        assert no_answer.receivers() is None


class TestGetEeprom:
    def _valid_block(self, payload: bytes | None = None) -> bytes:
        data = payload if payload is not None else bytes(
            range(256)) * (EEPROM_SIZE // 256)
        assert len(data) == EEPROM_SIZE
        crc = crc_calculate(data)
        return data + struct.pack(">H", crc)

    def test_returns_4096_bytes_with_crc_stripped(self):
        drv = _driver_with(self._valid_block(), ack=0x06)
        result = drv.get_eeprom()
        assert result is not None
        assert len(result) == EEPROM_SIZE

    def test_payload_round_trips(self):
        payload = bytes((i * 7) % 256 for i in range(EEPROM_SIZE))
        drv = _driver_with(self._valid_block(payload), ack=0x06)
        assert drv.get_eeprom() == payload

    def test_short_read_returns_none(self):
        drv = _driver_with(b"\x00" * 100, ack=0x06)
        assert drv.get_eeprom() is None

    def test_bad_crc_returns_none(self):
        data = bytes(EEPROM_SIZE)
        drv = _driver_with(data + b"\xDE\xAD", ack=0x06)
        assert drv.get_eeprom() is None

    def test_no_ack_raises(self):
        drv = _driver_with(self._valid_block(), ack=0x21)   # NAK
        with pytest.raises(ConnectionError, match="GETEE: no ACK"):
            drv.get_eeprom()

    def test_known_offsets_readable_from_dump(self):
        """A dump is only useful if documented addresses land where the
        EEPROM map says. 0x0F is elevation in feet."""
        data = bytearray(EEPROM_SIZE)
        struct.pack_into("<h", data, 0x0F, 265)
        drv = _driver_with(self._valid_block(bytes(data)), ack=0x06)
        dump = drv.get_eeprom()
        assert struct.unpack_from("<h", dump, 0x0F)[0] == 265


class TestDriverInterface:
    @pytest.mark.parametrize("name", [
        "receivers", "async_receivers", "get_eeprom", "async_get_eeprom",
    ])
    def test_driver_exposes(self, name):
        assert hasattr(VantageDriver, name), f"missing {name}"

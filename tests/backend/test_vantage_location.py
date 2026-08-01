"""Tests for station latitude/longitude writes (Ref #221).

Lat/lon live at EEPROM 0x0B and 0x0D as signed 16-bit TENTHS of a degree.
The manual (§IX.7) is emphatic that NEWSETUP must follow a write or the
change may not take effect, so set_location() issues it by default.

The encoding tests matter more than they look. A wrong sign convention
puts the station in the wrong hemisphere, and the console uses these
values for its own sunrise/sunset and pressure correction — so the
failure mode is quietly wrong derived data rather than an error.
"""

import struct

import pytest

from app.protocol.vantage.commands import cmd_newsetup
from app.protocol.vantage.driver import VantageDriver


def test_newsetup_command_format():
    assert cmd_newsetup() == b"NEWSETUP\n"


class _RecordingDriver(VantageDriver):
    """Captures EEPROM writes and commands instead of touching a port."""

    def __init__(self):
        super().__init__("/dev/null", 19200)
        self.writes: list[tuple[int, bytes]] = []
        self.sent: list[bytes] = []
        self.write_ok = True
        self.status_ok = True
        self._wakeup = lambda: None

        class _S:
            is_open = True

            def flush(_self):
                pass

            def send(_self, data):
                self.sent.append(data)

            def receive(_self, n):
                return b""

            def receive_byte(_self):
                return None

        self.serial = _S()

    def _eeprom_write(self, address, data):
        self.writes.append((address, data))
        return self.write_ok

    def _read_status_reply(self, timeout_reads=24):
        return self.status_ok


class TestEncoding:
    """Tenths of a degree, signed. Negative lat = south, negative lon = west."""

    @pytest.mark.parametrize("lat,lon,exp_lat,exp_lon", [
        (35.4, -78.6, 354, -786),      # the real station
        (0.0, 0.0, 0, 0),
        (45.0, 90.0, 450, 900),
        (-33.9, 151.2, -339, 1512),    # southern + eastern
        (-45.0, -70.0, -450, -700),    # southern + western
        (90.0, 180.0, 900, 1800),      # extremes
        (-90.0, -180.0, -900, -1800),
    ])
    def test_degrees_to_tenths(self, lat, lon, exp_lat, exp_lon):
        drv = _RecordingDriver()
        assert drv.set_location(lat, lon) is True
        addrs = {a: d for a, d in drv.writes}
        assert struct.unpack("<h", addrs[0x0B])[0] == exp_lat
        assert struct.unpack("<h", addrs[0x0D])[0] == exp_lon

    def test_rounds_to_nearest_tenth(self):
        """0.1 deg is the format's precision, not a bug in this code."""
        drv = _RecordingDriver()
        drv.set_location(35.38, -78.64)
        addrs = {a: d for a, d in drv.writes}
        assert struct.unpack("<h", addrs[0x0B])[0] == 354    # 35.38 -> 35.4
        assert struct.unpack("<h", addrs[0x0D])[0] == -786   # -78.64 -> -78.6

    def test_writes_to_the_documented_addresses(self):
        drv = _RecordingDriver()
        drv.set_location(35.4, -78.6)
        assert [a for a, _ in drv.writes] == [0x0B, 0x0D]

    def test_each_write_is_two_bytes(self):
        drv = _RecordingDriver()
        drv.set_location(35.4, -78.6)
        assert all(len(d) == 2 for _, d in drv.writes)


class TestValidation:
    @pytest.mark.parametrize("lat", [90.1, -90.1, 1000, -1000])
    def test_latitude_range(self, lat):
        drv = _RecordingDriver()
        with pytest.raises(ValueError, match="latitude out of range"):
            drv.set_location(lat, 0.0)

    @pytest.mark.parametrize("lon", [180.1, -180.1, 5000])
    def test_longitude_range(self, lon):
        drv = _RecordingDriver()
        with pytest.raises(ValueError, match="longitude out of range"):
            drv.set_location(0.0, lon)

    def test_nothing_written_when_rejected(self):
        drv = _RecordingDriver()
        with pytest.raises(ValueError):
            drv.set_location(999, 0.0)
        assert drv.writes == []


class TestNewsetup:
    def test_issued_by_default(self):
        drv = _RecordingDriver()
        drv.set_location(35.4, -78.6)
        assert b"NEWSETUP\n" in drv.sent

    def test_can_be_deferred_for_batching(self):
        drv = _RecordingDriver()
        drv.set_location(35.4, -78.6, newsetup=False)
        assert b"NEWSETUP\n" not in drv.sent
        assert len(drv.writes) == 2      # values still written

    def test_failure_reported_even_though_values_are_written(self):
        """A silent 'success' here would leave the caller believing the
        console had picked the change up when it may not have."""
        drv = _RecordingDriver()
        drv.status_ok = False
        assert drv.set_location(35.4, -78.6) is False
        assert len(drv.writes) == 2

    def test_standalone_newsetup(self):
        drv = _RecordingDriver()
        assert drv.newsetup() is True
        assert b"NEWSETUP\n" in drv.sent


class TestWriteFailure:
    def test_returns_false_and_skips_newsetup(self):
        drv = _RecordingDriver()
        drv.write_ok = False
        assert drv.set_location(35.4, -78.6) is False
        assert b"NEWSETUP\n" not in drv.sent


class TestReadback:
    def test_round_trip_decodes_to_degrees(self):
        drv = _RecordingDriver()
        store = {0x0B: struct.pack("<h", 354),
                 0x0D: struct.pack("<h", -786)}
        drv._eeprom_read = lambda addr, n: store.get(addr)
        assert drv.read_location() == (35.4, -78.6)

    def test_southern_western_round_trip(self):
        drv = _RecordingDriver()
        store = {0x0B: struct.pack("<h", -339),
                 0x0D: struct.pack("<h", -786)}
        drv._eeprom_read = lambda addr, n: store.get(addr)
        assert drv.read_location() == (-33.9, -78.6)

    def test_none_when_read_fails(self):
        drv = _RecordingDriver()
        drv._eeprom_read = lambda addr, n: None
        assert drv.read_location() is None


class TestDriverInterface:
    @pytest.mark.parametrize("name", [
        "set_location", "read_location", "newsetup",
        "async_set_location", "async_read_location", "async_newsetup",
    ])
    def test_exposed(self, name):
        assert hasattr(VantageDriver, name), f"missing {name}"

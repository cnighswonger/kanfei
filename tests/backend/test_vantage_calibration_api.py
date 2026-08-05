"""Vantage temperature/humidity calibration through IPC and the API.

Distinct from barometer calibration: a Vantage adjusts temperature and
humidity by per-sensor EEPROM offsets applied through CALED/CALFIX, while
the barometer is BAR=.  Conflating the two is the terminology trap the
barometer handler docstring warns about, so this asserts they stay
separate surfaces.
"""

import pytest

from app.api.station import _cal_error
from app.ipc import protocol as ipc
from app.protocol.base import CAP_CALIBRATION_RW
from app.protocol.link_driver import LinkDriver
from app.protocol.vantage.driver import VantageDriver
from app.protocol.vantage.eeprom import (
    CAL_INSIDE_HUM,
    CAL_INSIDE_TEMP,
    CAL_OUTSIDE_HUM,
    CAL_OUTSIDE_TEMP,
)


class FakeSerial:
    is_open = True
    timeout = 5.0

    def flush(self): pass
    def set_timeout(self, t): self.timeout = t
    def send(self, data): pass
    def receive(self, n): return b""
    def receive_byte(self): return None


class TestReadCalibration:
    @staticmethod
    def _driver(raw=b"\x00"):
        drv = VantageDriver("/dev/null", 19200)
        drv._eeprom_read = lambda addr, n: raw
        return drv

    def test_offsets_are_signed(self):
        """0xFA is -6, not 250.  An unsigned read would show a -0.6 °F
        trim as +25 °F."""
        assert self._driver(b"\xfa").read_calibration()["outside_temp"] == -6

    def test_zero_is_a_real_value(self):
        assert self._driver(b"\x00").read_calibration()["inside_temp"] == 0

    def test_an_unreadable_field_is_omitted_not_zeroed(self):
        """Zero is a legitimate calibration.  Reporting an unreadable
        field as zero would make "no offset" and "could not read" look
        identical."""
        drv = VantageDriver("/dev/null", 19200)
        drv._eeprom_read = lambda addr, n: (
            b"" if addr == CAL_OUTSIDE_TEMP.address else b"\x05"
        )
        offsets = drv.read_calibration()
        assert "outside_temp" not in offsets
        assert offsets["inside_temp"] == 5

    def test_all_unreadable_returns_none(self):
        assert self._driver(b"").read_calibration() is None

    def test_covers_the_four_settable_fields(self):
        """Extra/soil/leaf slots exist in the block but are inert without
        the hardware, so they are deliberately excluded."""
        names = {n for n, _ in VantageDriver("/dev/null", 19200).CALIBRATION_FIELDS}
        assert names == {
            "inside_temp", "outside_temp", "inside_humidity", "outside_humidity",
        }


class TestCapabilityGate:
    @staticmethod
    def _daemon(driver):
        from logger_main import LoggerDaemon
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = driver
        return daemon

    def test_ipc_commands_registered(self):
        assert ipc.CMD_READ_VANTAGE_CAL == "read_vantage_cal"
        assert ipc.CMD_WRITE_VANTAGE_CAL == "write_vantage_cal"
        assert ipc.CMD_CLEAR_VANTAGE_CAL == "clear_vantage_cal"

    @pytest.mark.asyncio
    async def test_legacy_is_refused_as_501(self):
        """LinkDriver advertises CAP_CALIBRATION_RW but has no
        async_read_calibration in the Vantage shape — the gate must catch
        that rather than blowing up on a missing attribute."""
        drv = LinkDriver("/dev/null", 2400)
        drv.serial = FakeSerial()
        drv._connected = True
        with pytest.raises(RuntimeError) as excinfo:
            await self._daemon(drv)._h_read_vantage_cal({})
        assert _cal_error(str(excinfo.value)).status_code == 501


class TestWriteHandler:
    @staticmethod
    def _daemon(**overrides):
        from logger_main import LoggerDaemon

        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial()
        drv._connected = True
        for name, value in overrides.items():
            setattr(drv, name, value)

        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = drv
        return daemon

    @staticmethod
    def _ok_driver(written):
        async def read():
            return dict(written)

        async def write(field, offset):
            written[{
                CAL_INSIDE_TEMP.address: "inside_temp",
                CAL_OUTSIDE_TEMP.address: "outside_temp",
                CAL_INSIDE_HUM.address: "inside_humidity",
                CAL_OUTSIDE_HUM.address: "outside_humidity",
            }[field.address]] = offset
            return True

        return {"async_read_calibration": read, "async_write_calibration": write}

    @pytest.mark.asyncio
    async def test_writes_the_named_field(self):
        written = {"outside_temp": 0}
        daemon = self._daemon(**self._ok_driver(written))
        result = await daemon._h_write_vantage_cal(
            {"field": "outside_temp", "offset": 25}
        )
        assert result["success"] is True
        assert result["after"]["outside_temp"] == 25

    @pytest.mark.asyncio
    async def test_an_unknown_field_is_rejected_by_name(self):
        """An allowlist, not an address computed from user input — and the
        error should name the field rather than leak an address."""
        daemon = self._daemon(**self._ok_driver({}))
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_write_vantage_cal({"field": "barometer", "offset": 5})
        assert "barometer" in str(excinfo.value)
        assert "inside_temp" in str(excinfo.value)

    @pytest.mark.asyncio
    async def test_barometer_is_not_a_field_here(self):
        """The barometer is BAR= and has its own panel.  Accepting it here
        would write an EEPROM byte that does nothing for pressure."""
        assert "barometer" not in type(self._daemon())._VANTAGE_CAL_FIELDS

    @pytest.mark.asyncio
    async def test_missing_arguments_map_to_400(self):
        daemon = self._daemon(**self._ok_driver({}))
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_write_vantage_cal({"field": "inside_temp"})
        assert _cal_error(str(excinfo.value)).status_code == 400

    @pytest.mark.asyncio
    async def test_a_refused_write_raises_and_reports_actual_state(self):
        async def read():
            return {"outside_temp": 7}

        async def write(field, offset):
            return False

        daemon = self._daemon(
            async_read_calibration=read, async_write_calibration=write,
        )
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_write_vantage_cal(
                {"field": "outside_temp", "offset": 25}
            )
        message = str(excinfo.value)
        assert "unchanged" not in message.lower()
        assert "7" in message

    @pytest.mark.asyncio
    async def test_driver_range_error_maps_to_400(self):
        async def read():
            return {}

        async def write(field, offset):
            raise ValueError("calibration offset must be -128..127, got 999")

        daemon = self._daemon(
            async_read_calibration=read, async_write_calibration=write,
        )
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_write_vantage_cal(
                {"field": "inside_temp", "offset": 999}
            )
        assert _cal_error(str(excinfo.value)).status_code == 400


class TestUnitsAreReported:
    @pytest.mark.asyncio
    async def test_read_states_its_units(self):
        """Temperature is TENTHS of a degree F.  A caller assuming whole
        degrees is off by a factor of ten, so the units ship with the
        data rather than living only in a docstring."""
        from logger_main import LoggerDaemon

        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial()
        drv._connected = True

        async def read():
            return {"outside_temp": 25}

        drv.async_read_calibration = read
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = drv

        result = await daemon._h_read_vantage_cal({})
        assert result["temp_units"] == "tenths_f"
        assert result["humidity_units"] == "percent"

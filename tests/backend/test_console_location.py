"""Console latitude/longitude (EEPROM 0x0B / 0x0D).

The console keeps its own location and uses it for its sunrise/sunset
calculation and pressure correction, so a disagreement with Kanfei's
configured location produces quietly wrong derived data rather than an
obvious failure (#261).
"""

import struct

import pytest

from app.ipc import protocol as ipc
from app.protocol.base import CAP_LOCATION_RW
from app.protocol.link_driver import LinkDriver
from app.protocol.vantage.driver import VantageDriver


class FakeSerial:
    """Replays a fixed reply; records what was sent."""

    is_open = True
    timeout = 5.0

    def __init__(self, reply: bytes = b"\x06"):
        self.sent: list[bytes] = []
        self._reply = reply
        self._pending = bytearray()

    def flush(self):
        pass

    def set_timeout(self, timeout):
        self.timeout = timeout

    def send(self, data: bytes):
        self.sent.append(data)
        self._pending += self._reply

    def receive(self, n: int) -> bytes:
        take = self._pending[:n]
        del self._pending[:n]
        return bytes(take)

    def receive_byte(self):
        data = self.receive(1)
        return data[0] if data else None


class TestCapabilityGate:
    def test_vantage_advertises_it(self):
        assert CAP_LOCATION_RW in VantageDriver("/dev/null", 19200).capabilities

    def test_legacy_does_not(self):
        """A legacy console has no EEPROM location to write."""
        assert CAP_LOCATION_RW not in LinkDriver("/dev/null", 2400).capabilities

    def test_ipc_commands_registered(self):
        assert ipc.CMD_READ_LOCATION == "read_location"
        assert ipc.CMD_SET_LOCATION == "set_location"


class TestTenthsOfADegree:
    """The format is signed tenths — ~11 km per step.

    Everything downstream depends on this: a reconcile check comparing at
    full precision reports a permanent disagreement on a station that is
    correctly configured, and copying the console's value back into Kanfei
    would discard up to ~5.6 km of precision Kanfei actually holds.
    """

    @pytest.mark.parametrize("degrees,tenths", [
        (35.3809, 354),      # the reference station: rounds to 35.4
        (-78.5982, -786),    # and -78.6
        (0.0, 0),
        (-45.55, -456),      # round-half-away-from-zero
        (89.99, 900),
    ])
    def test_encoding(self, degrees, tenths):
        assert int(round(degrees * 10)) == tenths

    def test_round_trip_loses_precision_as_expected(self):
        """Pins the actual loss, so a future 'improvement' to the encoding
        has to confront what the hardware format can hold."""
        for original, stored in ((35.3809, 35.4), (-78.5982, -78.6)):
            assert struct.unpack("<h", struct.pack("<h", round(original * 10)))[0] / 10.0 == stored

    def test_a_correctly_configured_station_compares_equal_at_resolution(self):
        """The comparison the UI must make.  At full precision these differ;
        at the console's own resolution they agree."""
        kanfei_lat, console_lat = 35.3809, 35.4
        assert kanfei_lat != console_lat
        assert round(kanfei_lat, 1) == console_lat


class TestDriverWrite:
    @staticmethod
    def _driver():
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(reply=b"\n\rOK\n\r")
        drv._wakeup = lambda: None
        drv._connected = True
        return drv

    @pytest.mark.parametrize("lat,lon", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0)])
    def test_out_of_range_raises_before_the_wire(self, lat, lon):
        drv = self._driver()
        with pytest.raises(ValueError):
            drv.set_location(lat, lon)
        assert drv.serial.sent == []

    def test_newsetup_is_issued(self):
        """§IX.7 requires NEWSETUP for latitude and longitude specifically;
        without it the write may not take effect."""
        drv = self._driver()
        drv._eeprom_write = lambda addr, data: True
        drv.set_location(35.3809, -78.5982)
        assert any(b"NEWSETUP" in s for s in drv.serial.sent)

    def test_newsetup_can_be_skipped_for_batching(self):
        drv = self._driver()
        drv._eeprom_write = lambda addr, data: True
        drv.set_location(35.3809, -78.5982, newsetup=False)
        assert not any(b"NEWSETUP" in s for s in drv.serial.sent)


class TestHandlers:
    @staticmethod
    def _daemon(driver):
        from logger_main import LoggerDaemon

        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = driver
        return daemon

    @staticmethod
    def _vantage(**overrides):
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial()
        drv._connected = True
        for name, value in overrides.items():
            setattr(drv, name, value)
        return drv

    @pytest.mark.asyncio
    async def test_read_returns_the_console_value_and_its_resolution(self):
        async def fake_read():
            return (35.4, -78.6)

        daemon = self._daemon(self._vantage(async_read_location=fake_read))
        result = await daemon._h_read_location({})
        assert result["latitude"] == 35.4
        assert result["longitude"] == -78.6
        # The caller cannot compare sensibly without knowing this.
        assert result["resolution_deg"] == 0.1

    @pytest.mark.asyncio
    async def test_legacy_is_refused_with_a_501_shaped_message(self):
        """`_cal_error` routes "does not support" to 501, so the wording
        matters as much as the refusal."""
        from app.api.station import _cal_error

        drv = LinkDriver("/dev/null", 2400)
        drv.serial = FakeSerial()
        drv._connected = True
        daemon = self._daemon(drv)

        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_read_location({})
        assert _cal_error(str(excinfo.value)).status_code == 501

    @pytest.mark.asyncio
    async def test_write_returns_what_the_console_now_holds(self):
        """Not what was sent.  The console rounds, so echoing the request
        would tell the user their station holds a value it does not."""
        state = {"loc": (0.0, 0.0)}

        async def fake_read():
            return state["loc"]

        async def fake_set(lat, lon, newsetup=True):
            state["loc"] = (round(lat, 1), round(lon, 1))
            return True

        daemon = self._daemon(self._vantage(
            async_read_location=fake_read, async_set_location=fake_set,
        ))
        result = await daemon._h_set_location({
            "latitude": 35.3809, "longitude": -78.5982,
        })

        assert result["success"] is True
        assert result["before"] == {"latitude": 0.0, "longitude": 0.0}
        # 35.3809 was sent; 35.4 is what the station has.
        assert result["after"] == {"latitude": 35.4, "longitude": -78.6}

    @pytest.mark.asyncio
    async def test_a_refused_write_raises_and_reports_actual_state(self):
        """Same rule as the barometer write (#252): never return normally
        on a failed write, and never claim the station is unchanged."""
        async def fake_read():
            return (12.3, 45.6)

        async def fake_set(lat, lon, newsetup=True):
            return False

        daemon = self._daemon(self._vantage(
            async_read_location=fake_read, async_set_location=fake_set,
        ))
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_set_location({"latitude": 1.0, "longitude": 2.0})

        message = str(excinfo.value)
        assert "unchanged" not in message.lower()
        assert "12.3" in message

    @pytest.mark.asyncio
    async def test_missing_arguments_are_rejected(self):
        from app.api.station import _cal_error

        daemon = self._daemon(self._vantage())
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_set_location({"latitude": 35.0})
        # "required" routes to 400, not 503.
        assert _cal_error(str(excinfo.value)).status_code == 400

    @pytest.mark.asyncio
    async def test_a_failed_post_write_read_reports_null_not_the_request(self):
        """If the console cannot be re-read after a successful write, say so.

        Echoing the sent value here would be the worst outcome: the user
        would see 35.3809 and believe the console holds it, when the
        console cannot hold that value at all and we do not know what it
        settled on.  Codex asked for this branch to be pinned (#265 R1).
        """
        async def fake_read():
            return None

        async def fake_set(lat, lon, newsetup=True):
            return True

        daemon = self._daemon(self._vantage(
            async_read_location=fake_read, async_set_location=fake_set,
        ))
        result = await daemon._h_set_location({
            "latitude": 35.3809, "longitude": -78.5982,
        })

        assert result["success"] is True
        assert result["after"] is None
        assert result["before"] is None

"""Tests for RAIN_YEAR_START (yearly-rain-reset month) on Vantage.

Single byte at EEPROM 0x2C, values 1..12.  The console uses this to
decide when the yearly rain accumulator drops back to zero — factory
default January, west-coast US practice is July.

Coverage: encoding, range enforcement, read-back of garbage register
values, capability declaration, IPC handler routing.  No hardware; each
test either records the write or supplies a stubbed EEPROM response.
"""

import pytest

from app.protocol.base import CAP_RAIN_SEASON_RW
from app.protocol.vantage.driver import VantageDriver
from app.protocol.vantage.eeprom import RAIN_YEAR_START


class _RecordingDriver(VantageDriver):
    """Captures EEPROM reads and writes without touching a serial port."""

    def __init__(self):
        super().__init__("/dev/null", 19200)
        self.writes: list[tuple[int, bytes]] = []
        # (address, n_bytes) -> bytes to return.
        self.eeprom_reads: dict[tuple[int, int], bytes] = {}
        self.write_ok = True
        self._wakeup = lambda: None

        class _S:
            is_open = True

            def flush(_self):
                pass

            def send(_self, data):
                pass

            def receive(_self, n):
                return b""

            def receive_byte(_self):
                return None

        self.serial = _S()

    def _eeprom_read(self, address, n_bytes):
        return self.eeprom_reads.get((address, n_bytes))

    def _eeprom_write(self, address, data):
        self.writes.append((address, data))
        return self.write_ok


class TestEncoding:
    """RAIN_YEAR_START is a single byte at 0x2C, values 1..12."""

    @pytest.mark.parametrize("month", list(range(1, 13)))
    def test_write_encodes_one_byte(self, month):
        drv = _RecordingDriver()
        assert drv.set_rain_year_start(month) is True
        assert drv.writes == [(RAIN_YEAR_START.address, bytes([month]))]

    def test_january_default(self):
        # Explicit pin — the factory default month is 1.  If the console
        # ships in the western-water-year build one day, this test will
        # need updating, but until then a write of 1 must encode as 0x01
        # at address 0x2C.
        drv = _RecordingDriver()
        drv.set_rain_year_start(1)
        assert drv.writes == [(0x2C, b"\x01")]

    def test_july_western_water_year(self):
        # The reason this feature exists.  Explicit test rather than
        # trusting the parametrize range because the west-coast use case
        # is the one that motivated adding the setter at all.
        drv = _RecordingDriver()
        drv.set_rain_year_start(7)
        assert drv.writes == [(0x2C, b"\x07")]


class TestRangeEnforcement:
    """Values outside 1..12 must be rejected client-side; the console
    would accept them and end up with a nonsensical setting."""

    @pytest.mark.parametrize("bad", [0, 13, 100, -1, -12])
    def test_out_of_range_raises(self, bad):
        drv = _RecordingDriver()
        with pytest.raises(ValueError, match="1-12"):
            drv.set_rain_year_start(bad)
        # Also confirm nothing hit the EEPROM.
        assert drv.writes == []


class TestReadBack:
    """Read reports legal months, rejects garbage."""

    @pytest.mark.parametrize("month", list(range(1, 13)))
    def test_read_returns_legal_month(self, month):
        drv = _RecordingDriver()
        drv.eeprom_reads[(RAIN_YEAR_START.address, 1)] = bytes([month])
        assert drv.read_rain_year_start() == month

    def test_read_rejects_zero(self):
        """Zero is the "never initialised" sentinel; must not be
        reported as month 0."""
        drv = _RecordingDriver()
        drv.eeprom_reads[(0x2C, 1)] = b"\x00"
        assert drv.read_rain_year_start() is None

    @pytest.mark.parametrize("bad", [13, 99, 0xFF])
    def test_read_rejects_out_of_range(self, bad):
        drv = _RecordingDriver()
        drv.eeprom_reads[(0x2C, 1)] = bytes([bad])
        assert drv.read_rain_year_start() is None

    def test_read_returns_none_on_eeprom_failure(self):
        drv = _RecordingDriver()
        # No eeprom_reads entry => _eeprom_read returns None
        assert drv.read_rain_year_start() is None


class TestCapability:
    """Every Vantage advertises the capability; nothing legacy does."""

    def test_vantage_advertises(self):
        drv = VantageDriver("/dev/null", 19200)
        assert CAP_RAIN_SEASON_RW in drv.capabilities

    def test_legacy_does_not_advertise(self):
        from app.protocol.link_driver import LinkDriver

        drv = LinkDriver("/dev/null", 2400)
        assert CAP_RAIN_SEASON_RW not in drv.capabilities


class TestIpcCommandsRegistered:
    """The two CMD constants are wired into the daemon's dispatch."""

    def test_cmd_constants_stable(self):
        # Wire contract — the string values are what the API sends to
        # the daemon.  Silent renames would break /api/station/rain-season.
        from app.ipc import protocol as ipc

        assert ipc.CMD_READ_RAIN_SEASON == "read_rain_season"
        assert ipc.CMD_SET_RAIN_SEASON == "set_rain_season"


class _FakeVantageForHandler:
    """Async-compatible fake for exercising the daemon's _h_set_rain_season.

    Distinct from _RecordingDriver above: that one tests the sync driver
    methods, this one tests the handler-level contract that a bare ACK is
    not sufficient.  The handler must ALSO check the read-back matches
    the requested month.
    """

    def __init__(
        self,
        *,
        write_returns: bool,
        read_before: int,
        read_after: int | None,
    ) -> None:
        from app.protocol.base import CAP_RAIN_SEASON_RW

        self._connected = True
        self.capabilities = {CAP_RAIN_SEASON_RW}
        self.station_name = "Fake Vue"
        self._write_returns = write_returns
        self._read_before = read_before
        self._read_after = read_after
        self._writes_done = 0

    @property
    def connected(self):
        return self._connected

    async def async_read_rain_year_start(self):
        return self._read_before if self._writes_done == 0 else self._read_after

    async def async_set_rain_year_start(self, _month):
        self._writes_done += 1
        return self._write_returns


def _daemon_with(drv):
    from logger_main import LoggerDaemon
    daemon = LoggerDaemon.__new__(LoggerDaemon)
    daemon.driver = drv
    return daemon


class TestHandlerReadBackContract:
    """Regression: _h_set_rain_season must fail on any read-back mismatch.

    #252 established this shape on the barometer BAR= path.  The console
    can NAK, ACK-then-drop the write, or ACK-then-write-a-different-value,
    and the operator has to be told which happened.  A bare ACK means
    nothing on its own.
    """

    @pytest.mark.asyncio
    async def test_ack_but_readback_still_old_raises(self):
        # The write ACKed but the register still holds the pre-write
        # value.  Classic silent no-op.
        drv = _FakeVantageForHandler(
            write_returns=True, read_before=1, read_after=1,
        )
        with pytest.raises(RuntimeError, match="does not reflect it"):
            await _daemon_with(drv)._h_set_rain_season({"month": 7})

    @pytest.mark.asyncio
    async def test_ack_but_readback_wrong_month_raises(self):
        # ACKed but ended up holding a completely different month.
        # Would be routed to the wrong address, or clobbered by a
        # concurrent console-side change.  Either way not success.
        drv = _FakeVantageForHandler(
            write_returns=True, read_before=1, read_after=4,
        )
        with pytest.raises(RuntimeError, match="does not reflect it"):
            await _daemon_with(drv)._h_set_rain_season({"month": 7})

    @pytest.mark.asyncio
    async def test_ack_but_readback_none_raises(self):
        # ACKed but the read-back failed / returned garbage.  We do not
        # know what the station has, so we cannot claim success.
        drv = _FakeVantageForHandler(
            write_returns=True, read_before=1, read_after=None,
        )
        with pytest.raises(RuntimeError, match="does not reflect it"):
            await _daemon_with(drv)._h_set_rain_season({"month": 7})

    @pytest.mark.asyncio
    async def test_nak_raises(self):
        # Sanity: pre-existing NAK branch still fires.  This was the only
        # failure mode the original handler caught.
        drv = _FakeVantageForHandler(
            write_returns=False, read_before=1, read_after=1,
        )
        with pytest.raises(RuntimeError, match="did not accept"):
            await _daemon_with(drv)._h_set_rain_season({"month": 7})

    @pytest.mark.asyncio
    async def test_ack_and_matching_readback_returns_success(self):
        # Happy path: ACK + read-back == requested month.
        drv = _FakeVantageForHandler(
            write_returns=True, read_before=1, read_after=7,
        )
        result = await _daemon_with(drv)._h_set_rain_season({"month": 7})
        assert result == {"success": True, "before": 1, "after": 7}

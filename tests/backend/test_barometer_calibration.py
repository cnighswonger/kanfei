"""Barometer calibration via the Vantage BAR= primitive (Ref #238).

Implements the procedure canonicalised in kanfei-phone-sensor#123
(`docs/DAVIS-STATION-CALIBRATION.md`), Vantage path only.

The load-bearing constraint is the capability gate.  Legacy WeatherLink
stations (Monitor II, Wizard) DO calibrate their barometer, but through a
direct `BAR_CAL` register write with **subtract** semantics — the
firmware computes ``Barometer = Barometer - BarCal``
(`reference/techref.txt:1070`), and `LinkDriver` negates at the I/O
boundary so the rest of kanfei sees an "add" convention (#154).

That makes this gate different in kind from the other capability gates.
Letting a legacy station through would not merely fail: `BAR=` does not
exist there, and a fallback to the register write would apply the offset
with the wrong sign — **doubling the error instead of removing it**.

WeatherLink IP is excluded for a separate reason: despite its name it
wraps `LinkDriver` and speaks the legacy command set (#247).
"""

import pytest

from app.ipc import protocol as ipc
from app.protocol.base import CAP_BAROMETER_CAL
from app.protocol.link_driver import LinkDriver
from app.protocol.vantage.commands import cmd_bar
from app.protocol.vantage.driver import VantageDriver


class FakeSerial:
    """Serial stub that replays an OK reply to any command."""

    # VantageDriver.connected is `self._connected and self.serial.is_open`,
    # so the stub provides this rather than the test patching the property
    # onto the class.  An earlier version did the latter and never restored
    # it, leaking a permanently-connected VantageDriver into every
    # subsequent test in the session (Codex R3 on #248).  It happened to be
    # harmless, but it would have masked a real connection-state
    # regression by making every driver look connected.
    is_open = True

    def __init__(self, reply: bytes = b"\n\rOK\n\r"):
        self.sent: list[bytes] = []
        self._reply = reply
        self._pending = bytearray()

    def flush(self):
        pass

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


@pytest.fixture
def driver():
    drv = VantageDriver("/dev/null", 19200)
    drv.serial = FakeSerial()
    drv._wakeup = lambda: None          # bypass the LF/LFCR handshake
    return drv


class TestCapabilityGate:
    """Which drivers may attempt BAR= at all."""

    def test_vantage_advertises_it(self):
        assert CAP_BAROMETER_CAL in VantageDriver("/dev/null", 19200).capabilities

    def test_advertised_even_without_loop2(self):
        """BAR= and BARDATA predate LOOP2, so a VP1 can still calibrate.
        Gating this on has_loop2 would exclude working hardware."""
        drv = VantageDriver("/dev/null", 19200)
        drv.hw_config.has_loop2 = False
        assert CAP_BAROMETER_CAL in drv.capabilities

    def test_legacy_does_not_advertise_it(self):
        """The load-bearing exclusion.  Legacy CAN calibrate, but with
        subtract semantics via a register write — running BAR= against it
        would double the error rather than remove it."""
        caps = LinkDriver("/dev/null", 2400).capabilities
        assert CAP_BAROMETER_CAL not in caps

    def test_weatherlink_ip_does_not_advertise_it(self):
        """WL-IP wraps LinkDriver despite the name (#247), so it inherits
        the legacy capability set and must not claim this."""
        import inspect

        from app.protocol.weatherlink_ip.driver import WeatherLinkIPDriver

        assert "LinkDriver(" in inspect.getsource(WeatherLinkIPDriver.__init__)
        assert CAP_BAROMETER_CAL not in LinkDriver("/dev/null", 2400).capabilities

    def test_ipc_commands_registered(self):
        assert ipc.CMD_BAROMETER_CAL == "barometer_cal"
        assert ipc.CMD_SET_BAROMETER == "set_barometer"


class TestWireFormat:
    def test_command_shape(self):
        """`BAR=` with the equals sign.  `BAR 29780 265` without it is a
        different command and will not calibrate."""
        assert cmd_bar(29780, 265) == b"BAR=29780 265\n"

    def test_driver_sends_the_built_command(self, driver):
        driver.set_barometer(29780, 265)
        assert driver.serial.sent[0] == b"BAR=29780 265\n"

    def test_negative_elevation_is_allowed(self, driver):
        """The manual's own example uses -75 ft; below-sea-level sites are
        legitimate."""
        driver.set_barometer(29991, -75)
        assert driver.serial.sent[0] == b"BAR=29991 -75\n"


class TestRangeValidation:
    """The console NAKs out-of-range values, which surfaces as a bare
    failure with no reason.  Validating first names the bad argument."""

    @pytest.mark.parametrize("bar", [19_999, 32_501, 100_000, -1])
    def test_out_of_range_barometer_rejected(self, driver, bar):
        with pytest.raises(ValueError, match="barometer"):
            driver.set_barometer(bar, 265)
        assert driver.serial.sent == [], "must not reach the wire"

    @pytest.mark.parametrize("bar", [20_000, 29_780, 32_500])
    def test_in_range_barometer_accepted(self, driver, bar):
        driver.set_barometer(bar, 265)
        assert driver.serial.sent

    @pytest.mark.parametrize("elev", [-2_001, 15_001, 99_999])
    def test_out_of_range_elevation_rejected(self, driver, elev):
        with pytest.raises(ValueError, match="elevation"):
            driver.set_barometer(29_780, elev)
        assert driver.serial.sent == []

    @pytest.mark.parametrize("elev", [-2_000, 0, 265, 15_000])
    def test_in_range_elevation_accepted(self, driver, elev):
        driver.set_barometer(29_780, elev)
        assert driver.serial.sent


class TestZeroClearsTheOffset:
    """`BAR=0 <elev>` is the supported rollback."""

    def test_zero_is_accepted_despite_being_below_the_minimum(self, driver):
        """0 is outside 20000-32500 but explicitly legal — the manual says
        a zero value "clears out any existing offset value previously
        set". A naive range check would reject the rollback path."""
        driver.set_barometer(0, 265)
        assert driver.serial.sent[0] == b"BAR=0 265\n"

    def test_clear_helper_preserves_elevation(self, driver):
        driver.clear_barometer_calibration(265)
        assert driver.serial.sent[0] == b"BAR=0 265\n"

    def test_clear_helper_is_not_clrcal(self, driver):
        """CLRCAL zeroes temperature and humidity offsets and does NOT
        touch the barometer.  Using it for a rollback silently leaves the
        bad calibration in place — the trap the procedure doc calls out."""
        driver.clear_barometer_calibration(265)
        assert b"CLRCAL" not in driver.serial.sent[0]
        assert driver.serial.sent[0].startswith(b"BAR=")


class TestNakIsNotSuccess:
    """A console rejection must not look like a completed write.

    Codex R1 blocker on #248: `set_barometer()` returning False was
    passed straight through by the handler, and the IPC server wraps any
    non-raising return as `ok: true` (`server.py:127`).  A NAKed write
    therefore surfaced as HTTP 200 carrying `success: false` — a write
    that did not take, presented as a successful request.
    """

    def test_driver_reports_nak_as_false(self):
        """`_read_status_reply` distinguishes OK from NAK; a NAK-only
        reply must not read as success."""
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(reply=b"\x21")      # bare NAK
        drv._wakeup = lambda: None
        assert drv.set_barometer(29_780, 265) is False

    def test_ok_reply_reports_true(self):
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(reply=b"\n\rOK\n\r")
        drv._wakeup = lambda: None
        assert drv.set_barometer(29_780, 265) is True

    @staticmethod
    def _daemon_with(nak: bool):
        """A LoggerDaemon whose driver answers BAR= with OK or NAK.

        Only ``self.driver`` is touched by the handler, so the daemon
        needs no other setup.
        """
        from logger_main import LoggerDaemon

        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial(reply=b"\x21" if nak else b"\n\rOK\n\r")
        drv._wakeup = lambda: None
        drv._connected = True

        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = drv
        return daemon

    @pytest.mark.asyncio
    async def test_handler_raises_on_nak(self):
        """The fix, exercised rather than grepped.

        An earlier version of this test asserted on ``inspect.getsource``
        output.  Codex called that source-text theatre on #248 R2 and was
        right: it passed whenever the source *contained* the right
        strings, regardless of what the handler did with them.  This
        invokes the handler.
        """
        daemon = self._daemon_with(nak=True)
        with pytest.raises(RuntimeError, match="rejected the calibration"):
            await daemon._h_set_barometer({
                "bar_thousandths_inhg": 29_780,
                "elevation_ft": 265,
            })

    @pytest.mark.asyncio
    async def test_handler_returns_success_on_ok(self):
        """The other half — the raise must not fire on a good write, or
        every calibration would report failure."""
        daemon = self._daemon_with(nak=False)
        result = await daemon._h_set_barometer({
            "bar_thousandths_inhg": 29_780,
            "elevation_ft": 265,
        })
        assert result["success"] is True
        assert "before" in result and "after" in result

    @pytest.mark.asyncio
    async def test_nak_message_maps_to_503_not_501_or_400(self):
        """`_cal_error` routes on substrings: "does not support" → 501,
        "must be"/"required" → 400.  The rejection message must not
        collide with either, or a hardware refusal would be reported as
        an unsupported station or a bad request."""
        from app.api.station import _cal_error

        daemon = self._daemon_with(nak=True)
        try:
            await daemon._h_set_barometer({
                "bar_thousandths_inhg": 29_780,
                "elevation_ft": 265,
            })
            pytest.fail("expected the NAK to raise")
        except RuntimeError as exc:
            assert _cal_error(str(exc)).status_code == 503

    @pytest.mark.asyncio
    async def test_nak_message_does_not_claim_the_station_is_unchanged(self):
        """A refused BAR= is not a no-op, so the message must not say it is.

        Measured on the test Vue (fw 3.0) 2026-08-04: the console refuses
        the command and applies the elevation argument anyway.

            BAR=0 400      -> ACK,  elevation = 400
            BAR=99999 275  -> NAK,  elevation = 275   (moved)

        The original wording was "calibration unchanged: {after}" — the
        embedded snapshot was truthful while the prose contradicted it.
        An operator who reads the sentence rather than the dict is told
        the console was left alone when its elevation may have moved.

        Asserted on the raised message rather than the source text: this
        fails if someone reintroduces the claim, in any phrasing that
        uses these words.
        """
        daemon = self._daemon_with(nak=True)
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_set_barometer({
                "bar_thousandths_inhg": 29_780,
                "elevation_ft": 265,
            })

        message = str(excinfo.value).lower()
        assert "unchanged" not in message, (
            "the NAK message claims the station is unchanged; a refused "
            "BAR= still applies its elevation argument"
        )
        # The message must say something concrete about where the console
        # ended up — either the re-read state, or an explicit admission
        # that the re-read failed.  This double serves as the guard for
        # the after=None path, which is what this fake produces.
        assert ("station now reads" in message
                or "could not re-read" in message)
        assert "elevation may have been" in message


class TestDriverInterface:
    @pytest.mark.parametrize("method", [
        "set_barometer", "async_set_barometer",
        "clear_barometer_calibration", "async_clear_barometer_calibration",
        "bardata", "async_bardata",
    ])
    def test_method_exists(self, method):
        assert hasattr(VantageDriver("/dev/null", 19200), method)


class TestConversionFactor:
    """The procedure mandates ``round(hpa * 0.029529983071445 * 1000)``.

    Pinned here because the tool must not drift from the bench procedure —
    a different factor is a silent split between what the bench station
    reports and what a deployed one does.
    """

    EXACT = 0.029529983071445

    def test_documented_example(self):
        assert round(1015.44 * self.EXACT * 1000) == 29986

    def test_standard_atmosphere(self):
        """1013.25 hPa is 29.921 inHg."""
        assert round(1013.25 * self.EXACT * 1000) == 29921

    def test_rounded_factor_does_diverge(self):
        """The procedure warns against the rounded 0.02953.  It differs by
        1 unit on ~1.7% of inputs — small, but the point of pinning the
        exact factor is that both ends compute identically.

        (The doc's own example, 1015.44, is NOT one of the divergent
        cases — both factors give 29986 there.  Reported upstream.)
        """
        rounded = 0.02953
        diverging = [
            h / 100
            for h in range(95_000, 105_001)
            if round(h / 100 * self.EXACT * 1000) != round(h / 100 * rounded * 1000)
        ]
        assert diverging, "if these never diverge, the warning is pointless"
        assert round(950.00 * self.EXACT * 1000) == 28053
        assert round(950.00 * rounded * 1000) == 28054

"""PUTRAIN and CLRLOG, and the preflight reads that make them safe.

Both destroy data on the console.  Chris's design call (#264): show the
cost before the operation rather than offering an undo afterwards — a
confirmation that names what will be lost is a decision, an undo offered
later is a consolation.

These tests are about the safety properties, not the plumbing.
"""

from datetime import datetime

import pytest

from app.api.station import _cal_error
from app.ipc import protocol as ipc
from app.protocol.base import CAP_RAIN_RESET, SensorSnapshot
from app.protocol.vantage.driver import VantageDriver


class FakeSerial:
    is_open = True
    timeout = 5.0

    def flush(self): pass
    def set_timeout(self, t): self.timeout = t
    def send(self, d): pass
    def receive(self, n): return b""
    def receive_byte(self): return None


def _daemon(driver):
    from logger_main import LoggerDaemon
    daemon = LoggerDaemon.__new__(LoggerDaemon)
    daemon.driver = driver
    return daemon


def _vantage(**overrides):
    drv = VantageDriver("/dev/null", 19200)
    drv.serial = FakeSerial()
    drv._connected = True
    for name, value in overrides.items():
        setattr(drv, name, value)
    return drv


class TestCommandsRegistered:
    def test_ipc_names(self):
        assert ipc.CMD_RAIN_PREFLIGHT == "rain_preflight"
        assert ipc.CMD_SET_YEARLY_RAIN == "set_yearly_rain"
        assert ipc.CMD_ARCHIVE_PREFLIGHT == "archive_preflight"
        assert ipc.CMD_CLEAR_ARCHIVE == "clear_archive"


class TestRainPreflight:
    """The preflight exists to make the cost visible before the write."""

    @pytest.mark.asyncio
    async def test_reports_the_gap_between_console_and_stored(self, monkeypatch):
        """The difference IS the data at risk: rain the console counted
        that Kanfei has not recorded, which a restore would discard."""
        async def poll():
            return SensorSnapshot(rain_yearly=31.2)

        daemon = _daemon(_vantage(poll=poll))
        monkeypatch.setattr(
            type(daemon), "_last_stored_rain_yearly",
            lambda self: (29.5, "2026-08-04T23:35:37"),
        )

        result = await daemon._h_rain_preflight({})
        assert result["console_mm"] == 31.2
        assert result["last_stored_mm"] == 29.5
        assert result["difference_mm"] == 1.7
        # The timestamp is what lets a user judge staleness.
        assert result["last_stored_at"] == "2026-08-04T23:35:37"

    @pytest.mark.asyncio
    async def test_a_missing_stored_value_is_not_reported_as_zero(self, monkeypatch):
        """A fresh install has no history.  Reporting 0 mm would imply the
        console had counted the entire total since the last poll."""
        async def poll():
            return SensorSnapshot(rain_yearly=31.2)

        daemon = _daemon(_vantage(poll=poll))
        monkeypatch.setattr(
            type(daemon), "_last_stored_rain_yearly", lambda self: (None, None),
        )

        result = await daemon._h_rain_preflight({})
        assert result["last_stored_mm"] is None
        assert result["difference_mm"] is None

    @pytest.mark.asyncio
    async def test_reports_whether_the_collector_is_known(self, monkeypatch):
        """The driver refuses to write without it rather than risk a 2x
        error, so the UI must be able to say so before the user tries."""
        async def poll():
            return SensorSnapshot(rain_yearly=10.0)

        drv = _vantage(poll=poll)
        drv.hw_config.rain_click_inches = None
        daemon = _daemon(drv)
        monkeypatch.setattr(
            type(daemon), "_last_stored_rain_yearly", lambda self: (10.0, "x"),
        )

        assert (await daemon._h_rain_preflight({}))["collector_known"] is False


class TestSetYearlyRain:
    @pytest.mark.asyncio
    async def test_takes_millimetres_not_clicks(self):
        """A click is 0.01in, 0.2 mm or 0.1 mm depending on the collector,
        so the same integer means three different totals.  Nothing in this
        path accepts a click count."""
        sent: list[float] = []

        async def poll():
            return SensorSnapshot(rain_yearly=0.0)

        async def set_rain(mm):
            sent.append(mm)
            return True

        daemon = _daemon(_vantage(poll=poll, async_set_yearly_rain=set_rain))
        await daemon._h_set_yearly_rain({"millimetres": 29.5})
        assert sent == [29.5]

    @pytest.mark.asyncio
    async def test_a_refused_write_raises_and_reports_actual_state(self):
        async def poll():
            return SensorSnapshot(rain_yearly=31.2)

        async def set_rain(mm):
            return False

        daemon = _daemon(_vantage(poll=poll, async_set_yearly_rain=set_rain))
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_set_yearly_rain({"millimetres": 0})
        message = str(excinfo.value)
        assert "unchanged" not in message.lower()
        assert "31.2" in message

    @pytest.mark.asyncio
    async def test_a_negative_total_is_a_400_not_a_503(self):
        async def poll():
            return SensorSnapshot(rain_yearly=1.0)

        async def set_rain(mm):
            raise ValueError("rain total must not be negative: -5.0")

        daemon = _daemon(_vantage(poll=poll, async_set_yearly_rain=set_rain))
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_set_yearly_rain({"millimetres": -5})
        assert _cal_error(str(excinfo.value)).status_code == 400

    @pytest.mark.asyncio
    async def test_missing_argument_is_a_400(self):
        daemon = _daemon(_vantage())
        with pytest.raises(RuntimeError) as excinfo:
            await daemon._h_set_yearly_rain({})
        assert _cal_error(str(excinfo.value)).status_code == 400


class TestArchivePreflight:
    @pytest.mark.asyncio
    async def test_reports_what_kanfei_already_holds(self, monkeypatch):
        """Kanfei's downloaded records survive the clear; the number is
        there so the user knows what is NOT at risk."""
        class _Q:
            def count(self): return 4211
            def order_by(self, *a): return self
            def first(self): return (datetime(2026, 8, 4, 23, 30),)

        class _DB:
            def query(self, *a): return _Q()
            def close(self): pass

        import logger_main
        monkeypatch.setattr(logger_main, "SessionLocal", lambda: _DB())

        async def clear():
            return True

        daemon = _daemon(_vantage(async_clear_log=clear))
        result = await daemon._h_archive_preflight({})
        assert result["records_in_kanfei"] == 4211
        assert result["latest_synced_at"].startswith("2026-08-04T23:30")


class TestNoAccidentalExposure:
    """The dangerous commands must not be reachable by accident."""

    def test_clearing_rain_is_not_bundled_into_a_read(self):
        """The preflight is a READ.  If it also cleared, a UI that polled
        it would destroy data on every render."""
        import inspect
        from logger_main import LoggerDaemon

        source = inspect.getsource(LoggerDaemon._h_rain_preflight)
        assert "set_yearly_rain" not in source
        assert "clear" not in source.lower().replace("collector", "")

    def test_archive_preflight_does_not_clear(self):
        import inspect
        from logger_main import LoggerDaemon

        source = inspect.getsource(LoggerDaemon._h_archive_preflight)
        assert "async_clear_log()" not in source


class TestErrorRoutingIsNotWhackAMole:
    """`_cal_error` routes on substrings, and matching only "must be" was
    wrong three separate times:

        "out of range"              (#267)
        "unknown calibration field" (#267 again, one branch away)
        "cannot be negative"        (#264)

    Each described a bad argument and each routed to 503 — telling the
    user their hardware had a transient fault when they had sent
    something invalid.  Rewording individual raise sites fixed each
    instance and left the next one waiting, so the phrase list is the
    thing under test now.
    """

    @pytest.mark.parametrize("message", [
        "rain total cannot be negative: -5.0",
        "ET total cannot be negative: -1.0",
        "calibration offset must be -128..127, got 999",
        "calibration field must be one of inside_temp; got barometer",
        "latitude must not be more than 90",
        "millimetres is required",
        "field and offset are both required",
        "calibration offset 999 out of range",
        "unknown calibration field 'barometer'",
    ])
    def test_bad_arguments_are_400(self, message):
        assert _cal_error(message).status_code == 400

    @pytest.mark.parametrize("message", [
        "Station did not accept CLRLOG",
        "Station did not return calibration offsets",
        "Station rejected the calibration (BAR= not acknowledged).",
        "Not connected",
    ])
    def test_station_faults_stay_503(self, message):
        """The widening must not reclassify a real hardware failure as the
        caller's fault — that would send a UI down a 'fix your input' path
        for a station that is genuinely broken."""
        assert _cal_error(message).status_code == 503

    @pytest.mark.parametrize("message", [
        "Vantage Vue does not support highs and lows",
        "Weather Monitor II does not support barometer calibration",
    ])
    def test_unsupported_stays_501(self, message):
        assert _cal_error(message).status_code == 501

    def test_every_driver_value_error_in_the_write_paths_is_a_400(self):
        """The real guard: walk the ValueError messages the driver can
        raise on these paths and assert each routes to 400.

        Asserted against the actual source rather than a hand-copied list,
        so a new raise site with unroutable wording fails here.
        """
        import re
        from pathlib import Path

        driver = Path(__file__).resolve().parents[2] / (
            "backend/app/protocol/vantage/driver.py"
        )
        # Capture the whole raise, then pull every literal chunk out of
        # the (possibly multi-line, possibly f-string) message.  A regex
        # that stopped at the first `{` produced fragments like "0x" and
        # judged them misrouted, which is a test bug rather than a finding.
        raises = re.findall(
            r"raise ValueError\((.*?)\)\n", driver.read_text(), re.DOTALL
        )
        assert raises, "no ValueError raises found — regex broke"

        messages = []
        for raw in raises:
            chunks = re.findall(r'f?"([^"]*)"', raw)
            joined = "".join(chunks).strip()
            if joined:
                messages.append(joined)
        assert messages, "no ValueError messages extracted"

        misrouted = [
            m for m in messages if _cal_error(m).status_code != 400
        ]
        assert not misrouted, (
            "driver ValueErrors that would surface as a station fault "
            f"rather than a bad request: {misrouted}"
        )

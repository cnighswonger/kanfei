"""HILOWS through IPC and the API.

The console keeps its own extremes, sampled continuously; Kanfei computes
its own from 10-second polls.  Surfacing both makes the disagreement
visible, which bounds what our sampling misses — the class of problem
behind #230, where a poisoned daily maximum survived all day.

Read-only by design: clearing the console's highs and lows is destructive
and deliberately not reachable from here.
"""

from datetime import time

import pytest

from app.api.station import _cal_error
from app.ipc import protocol as ipc
from app.protocol.base import CAP_HILOWS
from app.protocol.link_driver import LinkDriver
from app.protocol.vantage.driver import VantageDriver
from app.protocol.vantage.hilows import HiLo, Period, VantageHighsLows


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
    # CAP_HILOWS is conditional on LOOP2, so a default driver would be
    # refused by the handler's own gate.
    drv.hw_config.has_loop2 = True
    for name, value in overrides.items():
        setattr(drv, name, value)
    return drv


class TestCapability:
    def test_ipc_command_registered(self):
        assert ipc.CMD_HIGHS_LOWS == "highs_lows"

    def test_vantage_with_loop2_advertises_it(self):
        drv = VantageDriver("/dev/null", 19200)
        drv.hw_config.has_loop2 = True
        assert CAP_HILOWS in drv.capabilities

    def test_a_vp1_without_loop2_does_not(self):
        """Unlike most capabilities this one is conditional, so absence is
        a normal state rather than a fault."""
        drv = VantageDriver("/dev/null", 19200)
        drv.hw_config.has_loop2 = False
        assert CAP_HILOWS not in drv.capabilities

    def test_legacy_advertises_it_but_cannot_do_it(self):
        """LinkDriver claims CAP_HILOWS and implements no hilows() — the
        advertise-what-you-cannot-do bug that motivated #221, live in the
        legacy driver since the initial commit.

        The capability itself is left alone: withdrawing it is a
        wire-contract change to a driver this PR does not otherwise
        touch.  Pinned here so the reason `_supports_hilows` cannot
        simply trust `capabilities` stays visible.
        """
        drv = LinkDriver("/dev/null", 2400)
        assert CAP_HILOWS in drv.capabilities
        assert not hasattr(drv, "async_hilows")

    @pytest.mark.asyncio
    async def test_legacy_is_refused_despite_advertising_the_capability(self):
        drv = LinkDriver("/dev/null", 2400)
        drv.serial = FakeSerial()
        drv._connected = True
        with pytest.raises(RuntimeError) as excinfo:
            await _daemon(drv)._h_highs_lows({})
        assert _cal_error(str(excinfo.value)).status_code == 501


class TestConfigGateMatchesCommandGate:
    """The `supported` map and the handler must answer identically.

    They did not: the handler checked capability *and* method, the config
    map reported the raw capability, so a legacy station advertised
    highs_lows, rendered the panel, called the endpoint, took a 501 and
    watched the panel disappear.  A support bit that can lie is worse
    than no support bit — the panel has already committed to existing by
    the time the truth arrives.
    """

    @staticmethod
    async def _supported_for(drv):
        from logger_main import LoggerDaemon

        drv.serial = FakeSerial()
        drv._connected = True
        if hasattr(drv, "_wakeup"):
            drv._wakeup = lambda: None

        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = drv
        daemon._archive_period = None
        daemon._sample_period = None
        result = await daemon._h_read_config({})
        return result["supported"]

    @pytest.mark.asyncio
    async def test_vantage_reports_true(self):
        drv = VantageDriver("/dev/null", 19200)
        drv.hw_config.has_loop2 = True
        assert (await self._supported_for(drv))["highs_lows"] is True

    @pytest.mark.asyncio
    async def test_legacy_reports_false(self):
        """The regression under test: CAP_HILOWS is present on
        LinkDriver, so anything reading the capability directly reports
        True here."""
        drv = LinkDriver("/dev/null", 2400)
        assert (await self._supported_for(drv))["highs_lows"] is False

    @pytest.mark.asyncio
    async def test_vp1_without_loop2_reports_false(self):
        drv = VantageDriver("/dev/null", 19200)
        drv.hw_config.has_loop2 = False
        assert (await self._supported_for(drv))["highs_lows"] is False

    @pytest.mark.asyncio
    async def test_the_two_gates_agree_for_every_driver(self):
        """Stated as the invariant rather than as three separate cases,
        so a driver added later is covered by construction."""
        vantage = VantageDriver("/dev/null", 19200)
        vantage.hw_config.has_loop2 = True
        vp1 = VantageDriver("/dev/null", 19200)
        vp1.hw_config.has_loop2 = False

        for drv in (vantage, vp1, LinkDriver("/dev/null", 2400)):
            advertised = (await self._supported_for(drv))["highs_lows"]
            # Only a 501 counts as refusal.  A supported driver gets past
            # the gate and then fails on FakeSerial, which is the pass
            # condition here — reaching the wire at all means the gate
            # let it through.
            try:
                await _daemon(drv)._h_highs_lows({})
                refused = False
            except RuntimeError as exc:
                refused = _cal_error(str(exc)).status_code == 501
            except Exception:
                refused = False
            assert advertised is not refused, (
                f"{type(drv).__name__} advertises {advertised} "
                f"but the handler refuses={refused}"
            )

    @pytest.mark.asyncio
    async def test_unsupported_maps_to_501(self):
        drv = VantageDriver("/dev/null", 19200)
        drv.serial = FakeSerial()
        drv._connected = True
        drv.hw_config.has_loop2 = False

        with pytest.raises(RuntimeError) as excinfo:
            await _daemon(drv)._h_highs_lows({})
        assert _cal_error(str(excinfo.value)).status_code == 501


class TestSerialisation:
    """`time` is not JSON-serialisable.  The IPC encoder would coerce it
    with `default=str`, giving "14:35:00" as a side effect rather than a
    decision — so the handler converts explicitly."""

    @staticmethod
    def _block_with_time():
        block = VantageHighsLows()
        block.outside_temp = Period(
            day=HiLo(high=31.5, low=18.2,
                     time_high=time(14, 35), time_low=time(5, 12)),
        )
        return block

    @pytest.mark.asyncio
    async def test_times_become_hh_mm_strings(self):
        async def fake():
            return self._block_with_time()

        result = await _daemon(_vantage(async_hilows=fake))._h_highs_lows({})
        day = result["highs_lows"]["outside_temp"]["day"]
        assert day["time_high"] == "14:35"
        assert day["time_low"] == "05:12"

    @pytest.mark.asyncio
    async def test_the_payload_is_json_serialisable(self):
        """The real assertion: whatever shape it has, it must survive
        json.dumps without a custom encoder."""
        import json

        async def fake():
            return self._block_with_time()

        result = await _daemon(_vantage(async_hilows=fake))._h_highs_lows({})
        json.dumps(result)      # raises TypeError if any `time` survived

    @pytest.mark.asyncio
    async def test_absent_readings_stay_null(self):
        """An unpopulated sensor must come back as null, not 0 — the
        distinction the parser works hard to preserve."""
        async def fake():
            return VantageHighsLows()

        result = await _daemon(_vantage(async_hilows=fake))._h_highs_lows({})
        day = result["highs_lows"]["outside_temp"]["day"]
        assert day["high"] is None
        assert day["time_high"] is None

    @pytest.mark.asyncio
    async def test_a_none_block_raises_rather_than_returning_empty(self):
        """Returning {} would look like a station with no extremes yet."""
        async def fake():
            return None

        with pytest.raises(RuntimeError, match="did not return"):
            await _daemon(_vantage(async_hilows=fake))._h_highs_lows({})


class TestReadOnly:
    def test_no_clear_command_is_exposed(self):
        """clear_highs/clear_lows exist on the driver but are destructive.
        Bundling them into a read-only view is how a display becomes a
        data-loss surface."""
        assert not hasattr(ipc, "CMD_CLEAR_HIGHS")
        assert not hasattr(ipc, "CMD_CLEAR_LOWS")

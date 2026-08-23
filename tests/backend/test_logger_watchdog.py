"""Poll-stall watchdog — sub-issue #475 of umbrella #472.

Pins the recovery behaviour when the poller's liveness clock stops
advancing:

- No poller → no-op.
- Stall below threshold → no-op.
- Stall above threshold → serialised forced reconnect.
- Wedged teardown → the exit-for-systemd backstop trips.

The watchdog's real signal is ``poll_stall_seconds`` on Poller.stats,
introduced in #473; the ``_FakePoller`` here is just a shape stub
whose stats() we can drive.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

import logger_main
from logger_main import LoggerDaemon

# Every test in this module is async; declaring the marker at module
# scope avoids a per-method decorator without depending on
# ``asyncio_mode = auto`` in the backend's pyproject (which pytest may
# not read when it picks up the workspace-root pyproject instead).
pytestmark = pytest.mark.asyncio


class _FakePoller:
    """Minimal Poller shape stub — the watchdog only reads
    ``stats`` and ``poll_interval``."""

    def __init__(self, stall_seconds, poll_interval: int = 10):
        self._stall = stall_seconds
        self.poll_interval = poll_interval

    @property
    def stats(self):
        return {"poll_stall_seconds": self._stall}


class _FakeDriver:
    """Minimal driver stub — the watchdog only reads ``connected``."""

    def __init__(self, connected: bool = True):
        self.connected = connected


@pytest.fixture
def daemon(monkeypatch) -> LoggerDaemon:
    """Fresh daemon; no driver attached.  Individual tests stub in
    just the moving parts they need.

    ``_is_setup_complete`` returns True by default so State-B
    reconnect logic can be exercised without wiring the DB.  Tests
    that need the false path monkey-patch it themselves.
    """
    d = LoggerDaemon()
    monkeypatch.setattr(d, "_is_setup_complete", lambda: True)
    return d


class TestWatchdogTickStallDetector:
    """State A: driver connected, poller running.  This is the
    original responsibility — detect a stalled poll clock and trigger
    a forced reconnect."""

    async def test_noop_when_stall_is_null(self, daemon):
        """Very short window between poller-constructed and run-loop
        -entered.  Treat as ok: the next tick will already see a
        concrete age and evaluate normally."""
        daemon.driver = _FakeDriver(connected=True)
        daemon.poller = _FakePoller(stall_seconds=None)
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_not_called()

    async def test_noop_when_stall_below_threshold(self, daemon):
        """Same 3 × poll_interval boundary as /api/health — 29 s of a
        10 s cycle is jitter, not stall."""
        daemon.driver = _FakeDriver(connected=True)
        daemon.poller = _FakePoller(stall_seconds=29.0, poll_interval=10)
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_not_called()

    async def test_forces_reconnect_when_stall_above_threshold(self, daemon):
        """3 × 10 s = 30 s; 31 s trips.  The watchdog's whole reason
        for existing — surface parity with /api/health at #473."""
        daemon.driver = _FakeDriver(connected=True)
        daemon.poller = _FakePoller(stall_seconds=31.0, poll_interval=10)
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_called_once()

    async def test_bad_poll_interval_uses_minimum_of_one(self, daemon):
        """Guard on the ``max(1, poll_interval)`` in _watchdog_tick —
        a driver bug that reports poll_interval=0 must not silently
        disable the watchdog by driving the threshold to 0 either.
        With floor=1 and multiplier=3, threshold=3s; 10 s trips."""
        daemon.driver = _FakeDriver(connected=True)
        daemon.poller = _FakePoller(stall_seconds=10.0, poll_interval=0)
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_called_once()


class TestWatchdogTickDriverlessRecovery:
    """State B: driver is None because a prior reconnect (initial or
    watchdog-forced) failed.  Uncovered by the 2026-08-23 vsits-02
    smoke test: the daemon sat idle for minutes because subsequent
    ticks fell through the ``poller is None`` guard the tick used to
    open with.  The new branch keeps trying so the daemon heals once
    the underlying hardware is back."""

    async def test_reconnects_when_driver_is_none_and_setup_complete(self, daemon):
        daemon.driver = None
        daemon.poller = None
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_called_once()

    async def test_skips_when_setup_incomplete(self, daemon, monkeypatch):
        """Fresh install waiting for the setup wizard — nothing to
        connect to yet, and a spurious reconnect attempt would drop
        errors into the journal for no reason."""
        daemon.driver = None
        daemon.poller = None
        monkeypatch.setattr(daemon, "_is_setup_complete", lambda: False)
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_not_called()

    async def test_skips_when_driver_mid_init(self, daemon):
        """``_connect`` sets ``self.driver = _create_driver(...)``
        before ``driver.connect()`` completes.  A watchdog tick that
        fires in that window sees ``driver is not None`` but
        ``driver.connected is False``.  State A's guard on
        ``driver.connected`` skips it; State B's guard on
        ``self.driver is None`` also skips it.  Result: no
        spurious re-entrant reconnect during the very startup we
        would otherwise interrupt."""
        daemon.driver = _FakeDriver(connected=False)
        daemon.poller = None
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        daemon._forced_reconnect.assert_not_called()

    async def test_skips_when_reconnect_lock_already_held(self, daemon):
        """Prior tick still running its own teardown+connect (or an
        operator IPC reconnect in flight).  A parallel State-B fire
        would double-teardown the same driver."""
        daemon.driver = None
        daemon.poller = None
        daemon._forced_reconnect = AsyncMock()
        # Acquire the lock as a stand-in for "another reconnect in
        # progress."  ``asyncio.Lock`` is per-loop; borrowing it in
        # the same test task is fine because we release before the
        # test ends.
        async with daemon._reconnect_lock:
            await daemon._watchdog_tick()
            daemon._forced_reconnect.assert_not_called()

    async def test_state_a_still_wins_over_state_b_when_both_apply(self, daemon):
        """A live poller reporting stall > threshold with driver
        connected must take the stall path, not the driverless-
        recovery path.  If state B ran here the daemon would tear
        down a healthy poller unnecessarily."""
        daemon.driver = _FakeDriver(connected=True)
        daemon.poller = _FakePoller(stall_seconds=1.0, poll_interval=10)
        daemon._forced_reconnect = AsyncMock()
        await daemon._watchdog_tick()
        # Stall below threshold — must NOT reconnect via either path.
        daemon._forced_reconnect.assert_not_called()


class TestForcedReconnect:
    async def test_teardown_then_connect_called_in_order(self, daemon, monkeypatch):
        calls = []
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/ttyUSB0", 19200),
        )
        async def _fake_teardown():
            calls.append("teardown")
        async def _fake_connect(port, baud):
            calls.append(("connect", port, baud))
        daemon._teardown_driver = _fake_teardown
        daemon._connect = _fake_connect
        await daemon._forced_reconnect()
        assert calls == ["teardown", ("connect", "/dev/ttyUSB0", 19200)]

    async def test_serialised_by_reconnect_lock(self, daemon, monkeypatch):
        """Two watchdog ticks racing into overlapping reconnects would
        double-teardown a driver mid-connect.  The second caller sees
        the lock held and returns without acting."""
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/null", 19200),
        )
        gate = asyncio.Event()
        async def _slow_teardown():
            await gate.wait()
        connect_mock = AsyncMock()
        daemon._teardown_driver = _slow_teardown
        daemon._connect = connect_mock

        t1 = asyncio.create_task(daemon._forced_reconnect())
        await asyncio.sleep(0)  # let t1 acquire the lock
        # Second caller now sees the lock held; must return without
        # touching connect.
        await daemon._forced_reconnect()
        assert connect_mock.call_count == 0
        gate.set()
        await t1
        assert connect_mock.call_count == 1

    async def test_exits_for_systemd_when_teardown_times_out(
        self, daemon, monkeypatch,
    ):
        """The exact backstop the watchdog issue calls for.  A wedged
        _io_lock (the class of failure #476 will address) means
        driver.disconnect() blocks forever; teardown then hangs; if we
        don't hand control to systemd, the daemon is stuck in the
        recovery attempt for its own failure mode.  Verified by
        patching os._exit."""
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/null", 19200),
        )
        # Shrink the timeout so the test isn't a 5 s wait.
        monkeypatch.setattr(logger_main, "FORCED_DISCONNECT_TIMEOUT", 0.05)

        async def _hangs_forever():
            await asyncio.Event().wait()

        daemon._teardown_driver = _hangs_forever
        connect_mock = AsyncMock()
        daemon._connect = connect_mock

        exit_calls: list[int] = []

        def _fake_exit(code):
            exit_calls.append(code)
            raise SystemExit(code)

        monkeypatch.setattr(logger_main.os, "_exit", _fake_exit)

        with pytest.raises(SystemExit) as exc_info:
            await daemon._forced_reconnect()
        assert exc_info.value.code == 1
        assert exit_calls == [1]
        # Reconnect must NOT have been attempted after the exit trigger.
        connect_mock.assert_not_called()

    async def test_ipc_reconnect_serialised_with_watchdog(
        self, daemon, monkeypatch,
    ):
        """The Codex R1 blocker on #475: `_reconnect_lock` was
        documented as serialising IPC-initiated reconnects against
        watchdog-initiated ones, but the handlers bypassed it.  This
        test pins the fix: an operator ``reconnect`` command that
        arrives mid-stall-recovery WAITS for the watchdog to finish
        rather than tearing down the same driver in parallel."""
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/null", 19200),
        )
        order: list[str] = []
        watchdog_teardown_gate = asyncio.Event()

        async def _watchdog_teardown():
            order.append("wd:teardown-start")
            await watchdog_teardown_gate.wait()
            order.append("wd:teardown-end")

        async def _connect(port, baud):
            order.append(f"connect({port})")

        daemon._teardown_driver = _watchdog_teardown
        daemon._connect = _connect

        # Watchdog acquires the lock; is parked inside teardown.
        wd_task = asyncio.create_task(daemon._forced_reconnect())
        await asyncio.sleep(0)  # let wd_task acquire lock and enter teardown
        assert order == ["wd:teardown-start"]

        # Operator reconnect arrives concurrently — it must wait for
        # the watchdog to release the lock, not run its own teardown
        # in parallel.
        op_task = asyncio.create_task(daemon._h_reconnect({}))
        # Give the operator a tick to try to acquire the lock.
        await asyncio.sleep(0)
        # Watchdog is still in teardown; the operator's teardown has
        # NOT started yet.
        assert order == ["wd:teardown-start"]

        # Release the watchdog's teardown.  It finishes, connects,
        # releases the lock; only THEN does the operator's turn run.
        watchdog_teardown_gate.set()
        # Swap the teardown for a fast one so the operator's turn
        # doesn't block on the same gate.
        async def _fast_teardown():
            order.append("op:teardown")
        daemon._teardown_driver = _fast_teardown

        await asyncio.gather(wd_task, op_task)
        assert order == [
            "wd:teardown-start",
            "wd:teardown-end",
            "connect(/dev/null)",  # watchdog reconnect
            "op:teardown",
            "connect(/dev/null)",  # operator reconnect
        ]

    async def test_reconnect_failure_is_logged_and_swallowed(
        self, daemon, monkeypatch, caplog,
    ):
        """If ``_connect`` raises we do NOT crash the watchdog — the
        next tick will trip again if the daemon is still stalled.
        Crashing here would silence the watchdog for the rest of the
        process's life."""
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/null", 19200),
        )
        async def _ok_teardown():
            return None
        async def _failing_connect(port, baud):
            raise RuntimeError("no station on this port")
        daemon._teardown_driver = _ok_teardown
        daemon._connect = _failing_connect
        # Should not raise.
        await daemon._forced_reconnect()

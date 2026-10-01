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


class TestConnectClearsDriverOnFailure:
    """Regression suite for the 2026-08-23 vsits-02 smoke re-test after
    #483.  ``_connect`` sets ``self.driver = _create_driver(...)`` BEFORE
    awaiting ``driver.connect()``.  If the wire handshake raises, the
    stale driver instance would strand the watchdog: State A's
    ``driver.connected`` guard skips, and State B's ``driver is None``
    guard skips too.  Result: no more automatic reconnect attempts.

    The fix clears ``self.driver`` on the failure path.  These tests
    pin the invariant so a future edit that changes the try/except
    shape doesn't silently reopen the hole."""

    class _RaisingDriver:
        """Driver stub whose ``connect`` raises the ENOENT the field
        smoke saw when the USB was gone."""

        connected = False

        async def connect(self):
            raise OSError(
                2,
                "could not open port /dev/ttyUSB0: [Errno 2] "
                "No such file or directory: '/dev/ttyUSB0'",
            )

        async def disconnect(self):
            return None

    async def test_self_driver_is_none_after_connect_raises(
        self, daemon, monkeypatch,
    ):
        """The load-bearing invariant.  After ``_connect`` raises,
        ``self.driver`` MUST be None so the watchdog's State-B guard
        fires on subsequent ticks."""
        monkeypatch.setattr(
            daemon, "_get_effective_config",
            lambda: {"station_driver_type": "vantage"},
        )
        monkeypatch.setattr(
            logger_main, "_create_driver",
            lambda driver_type, config: self._RaisingDriver(),
        )
        with pytest.raises(OSError):
            await daemon._connect("/dev/ttyUSB0", 19200)
        assert daemon.driver is None, (
            "Stale driver reference survives a failed connect — "
            "watchdog State-B will never fire"
        )

    async def test_watchdog_state_b_fires_after_a_failed_reconnect(
        self, daemon, monkeypatch,
    ):
        """End-to-end version of the invariant.  ``_forced_reconnect``
        runs, ``_connect`` fails, next ``_watchdog_tick`` sees
        ``self.driver is None`` and calls ``_forced_reconnect`` again.
        Before the fix, the failed reconnect left ``self.driver`` set
        and the second tick silently skipped."""
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/null", 19200),
        )
        monkeypatch.setattr(
            daemon, "_get_effective_config",
            lambda: {"station_driver_type": "vantage"},
        )
        monkeypatch.setattr(
            logger_main, "_create_driver",
            lambda driver_type, config: self._RaisingDriver(),
        )
        # First reconnect fails — ``_connect`` catches the raise,
        # runs the real ``_teardown_driver`` (which null-safes every
        # field so a no-poller / no-task daemon is fine), and clears
        # ``self.driver``.  ``_forced_reconnect``'s outer catch logs
        # the swallowed exception.
        await daemon._forced_reconnect()
        assert daemon.driver is None
        # Now a subsequent watchdog tick must trip State B and try
        # again — that's what was broken in the field.
        reconnect_mock = AsyncMock()
        daemon._forced_reconnect = reconnect_mock
        await daemon._watchdog_tick()
        reconnect_mock.assert_called_once()


class TestConnectClearsDriverOnPostHandshakeFailure:
    """Codex R1 on #485 extension: the ``_connect`` cleanup must also
    catch failures AFTER ``driver.connect()`` succeeded but before the
    poller task is started.  A raise from
    ``async_read_archive_period`` / ``async_write_station_time`` /
    ``Poller`` construction used to leave the daemon in the same
    stranded state — driver connected, no poller, both watchdog
    branches silently skip.  These tests pin the widened cleanup."""

    class _ConnectOKThenFailDriver:
        """Driver whose ``connect`` succeeds but whose subsequent
        ``async_write_station_time`` raises.  Any post-handshake await
        in ``_connect`` would do; clock sync is the one every driver
        with the capability calls."""

        connected = False

        async def connect(self):
            self.connected = True

        async def disconnect(self):
            self.connected = False

        async def async_write_station_time(self, now):
            raise OSError(5, "Input/output error")

        # Station identity metadata that ``_connect`` logs on success.
        station_name = "FakeStation"

        class _HwConfig:
            station_type = None
        hw_config = _HwConfig()

    async def test_teardown_runs_when_post_handshake_await_raises(
        self, daemon, monkeypatch,
    ):
        """A raise after ``driver.connect()`` must clear self.driver
        just like a raise in ``driver.connect()`` itself.  Otherwise
        the watchdog dead zone Codex R1 flagged reopens."""
        monkeypatch.setattr(
            daemon, "_get_effective_config",
            lambda: {"station_driver_type": "vantage"},
        )
        monkeypatch.setattr(
            logger_main, "_create_driver",
            lambda driver_type, config: self._ConnectOKThenFailDriver(),
        )
        with pytest.raises(OSError):
            await daemon._connect("/dev/ttyUSB0", 19200)
        assert daemon.driver is None, (
            "Post-handshake raise left a connected driver on self — "
            "watchdog State-B still can't recover"
        )
        assert daemon.poller is None
        assert daemon.poller_task is None


class TestCp210xUsbResetEscalation:
    """CP210x wedge recovery escalation (#501).

    After N consecutive ``_forced_reconnect`` failures, the watchdog
    assumes the CP2102N inside the Vue console is in the AN571 errata
    state — enumerated but refusing every ``cp210x_open`` with -71
    EPROTO or -110 ETIMEDOUT — and issues USBDEVFS_RESET on the raw
    USB node before the next open attempt.  A success resets the
    streak; past the upper cap the escalation stops to avoid flooding
    the log on a truly dead cable.

    These tests pin the escalation ladder shape without touching real
    USB — ``_attempt_usbdevfs_reset`` is monkey-patched to a counter.
    The sysfs-walking inside it has its own dedicated test below.
    """

    class _RaisingDriver:
        connected = False

        async def connect(self):
            raise OSError(5, "[Errno 5] Input/output error: '/dev/ttyUSB0'")

        async def disconnect(self):
            return None

    def _wire_reconnect_env(self, daemon, monkeypatch):
        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/ttyUSB0", 19200),
        )
        monkeypatch.setattr(
            daemon, "_get_effective_config",
            lambda: {"station_driver_type": "vantage"},
        )
        monkeypatch.setattr(
            logger_main, "_create_driver",
            lambda driver_type, config: self._RaisingDriver(),
        )

    async def test_streak_starts_at_zero_and_no_reset_on_first_two_failures(
        self, daemon, monkeypatch,
    ):
        """First and second failures must NOT trigger a USB reset.  The
        chip wedge is a repeat-failure signature; a single open failure
        after a transient hiccup must not escalate to the stronger
        remedy."""
        self._wire_reconnect_env(daemon, monkeypatch)
        reset_mock = AsyncMock()
        monkeypatch.setattr(daemon, "_attempt_usbdevfs_reset", reset_mock)

        await daemon._forced_reconnect()
        assert daemon._reconnect_fail_streak == 1
        reset_mock.assert_not_called()

        await daemon._forced_reconnect()
        assert daemon._reconnect_fail_streak == 2
        reset_mock.assert_not_called()

    async def test_reset_fires_in_escalation_window(
        self, daemon, monkeypatch,
    ):
        """Escalation window is prior-streak ∈ [3, 6): the reset fires
        BEFORE the connect attempt, so the first fire is on the 4th
        attempt (after 3 prior failures).  Verifies that first-fire
        boundary, the still-escalating step, and the final step before
        the upper cap."""
        self._wire_reconnect_env(daemon, monkeypatch)
        reset_mock = AsyncMock()
        monkeypatch.setattr(daemon, "_attempt_usbdevfs_reset", reset_mock)

        # Burn three failures — reset must NOT fire on any of these
        # (the check runs before connect; streak starts at 0 on each).
        for _ in range(3):
            await daemon._forced_reconnect()
        assert reset_mock.call_count == 0
        assert daemon._reconnect_fail_streak == 3

        # Attempts 4-6 all run with streak ∈ {3, 4, 5}, each in-window.
        for _ in range(3):
            await daemon._forced_reconnect()
        assert reset_mock.call_count == 3
        assert daemon._reconnect_fail_streak == 6

    async def test_no_reset_once_give_up_cap_reached(
        self, daemon, monkeypatch,
    ):
        """Past the upper cap we stop ioctl-ing.  A truly dead cable
        can't be re-animated by a reset storm, and the log noise just
        hides the real problem."""
        self._wire_reconnect_env(daemon, monkeypatch)
        reset_mock = AsyncMock()
        monkeypatch.setattr(daemon, "_attempt_usbdevfs_reset", reset_mock)

        # Simulate the daemon already past the give-up threshold.
        daemon._reconnect_fail_streak = logger_main.USB_RESET_GIVE_UP_AFTER
        await daemon._forced_reconnect()
        reset_mock.assert_not_called()
        # Streak keeps climbing so /api/health still has a monotonic
        # signal operators can watch for "stuck".
        assert daemon._reconnect_fail_streak == (
            logger_main.USB_RESET_GIVE_UP_AFTER + 1
        )

    async def test_streak_resets_on_successful_reconnect(
        self, daemon, monkeypatch,
    ):
        """A successful ``_connect`` wipes the streak back to zero so
        the NEXT wedge gets the full escalation ladder from scratch.
        Pins the invariant that recovery is not a one-shot event."""
        # Pretend we are mid-escalation after a prior sequence.
        daemon._reconnect_fail_streak = 4

        class _OKDriver:
            connected = False
            station_name = "Fake"

            class _Hw:
                station_type = None
            hw_config = _Hw()

            async def connect(self):
                self.connected = True

            async def disconnect(self):
                self.connected = False

        monkeypatch.setattr(
            daemon, "_get_serial_config", lambda: ("/dev/ttyUSB0", 19200),
        )
        monkeypatch.setattr(
            daemon, "_get_effective_config",
            lambda: {"station_driver_type": "vantage", "poll_interval": 10},
        )
        monkeypatch.setattr(
            logger_main, "_create_driver",
            lambda driver_type, config: _OKDriver(),
        )
        reset_mock = AsyncMock()
        monkeypatch.setattr(daemon, "_attempt_usbdevfs_reset", reset_mock)
        # Streak is 4 — within the escalation window, so a reset would
        # fire before the (succeeding) connect.  Fine; what we're
        # pinning is what happens AFTER success.
        await daemon._forced_reconnect()
        assert daemon._reconnect_fail_streak == 0
        # And the poller got created — i.e. the success path really
        # did complete, not just skip past the counter line.
        assert daemon.poller is not None

    async def test_usbdevfs_reset_resolves_sys_path_and_issues_ioctl(
        self, daemon, monkeypatch, tmp_path,
    ):
        """``_attempt_usbdevfs_reset`` walks /sys/class/tty/<name>
        upward until it finds busnum+devnum, then opens
        /dev/bus/usb/BBB/DDD and ioctls USBDEVFS_RESET.  Faking the
        sysfs tree lets this run on any CI host — no real USB needed.
        """
        import fcntl as _fcntl

        # Fake sysfs: /sys/class/tty/ttyFAKE → .../usbFAKE/ttyFAKE/tty/ttyFAKE
        # with busnum+devnum two levels up.
        sys_root = tmp_path / "sys"
        usb_dev = sys_root / "devices" / "usbFAKE"
        tty_leaf = usb_dev / "ttyFAKE" / "tty" / "ttyFAKE"
        tty_leaf.mkdir(parents=True)
        (usb_dev / "busnum").write_text("3\n")
        (usb_dev / "devnum").write_text("17\n")
        class_tty = sys_root / "class" / "tty"
        class_tty.mkdir(parents=True)
        (class_tty / "ttyFAKE").symlink_to(tty_leaf)

        # Point the helper's resolver at the fake tree.  monkey-patch
        # the Path constructor only inside the helper by patching
        # /sys/class/tty via a replacement Path.
        import pathlib
        real_path_cls = pathlib.Path
        fake_root = sys_root

        def _fake_path(arg):
            s = str(arg)
            if s.startswith("/sys/class/tty"):
                return real_path_cls(str(fake_root) + s[4:])  # /sys → tmp/sys
            return real_path_cls(arg)

        monkeypatch.setattr("logger_main.Path", _fake_path, raising=False)

        # Intercept os.open and fcntl.ioctl so no real device is touched.
        opened_nodes: list[str] = []
        ioctl_calls: list[tuple[int, int]] = []

        def _fake_open(path, flags, *args, **kwargs):
            opened_nodes.append(path)
            return 999  # sentinel fd

        def _fake_ioctl(fd, request, arg):
            ioctl_calls.append((fd, request))
            return 0

        def _fake_close(fd):
            assert fd == 999

        monkeypatch.setattr(logger_main.os, "open", _fake_open)
        monkeypatch.setattr(logger_main.os, "close", _fake_close)
        monkeypatch.setattr(_fcntl, "ioctl", _fake_ioctl)

        await daemon._attempt_usbdevfs_reset("/dev/ttyFAKE")

        assert opened_nodes == ["/dev/bus/usb/003/017"]
        assert ioctl_calls == [(999, logger_main._USBDEVFS_RESET)]
        assert daemon._usb_reset_count == 1
        assert daemon._last_usb_reset_at is not None

    async def test_resolver_soft_returns_on_symlink_loop(
        self, daemon, monkeypatch,
    ):
        """Python 3.10-3.12 raises ``RuntimeError`` (not ``OSError``)
        when ``Path.resolve()`` hits an infinite symlink loop.  If the
        helper doesn't catch it, the raise escapes ``_forced_reconnect``
        and the watchdog's whole recovery cadence stops — exactly the
        regression this ladder exists to prevent (Codex PR 557 R1
        blocker)."""

        class _LoopingPath:
            """Minimal Path stand-in whose ``resolve`` raises
            ``RuntimeError``, matching the stdlib's behaviour on 3.10-
            3.12 when it detects a cycle."""

            def __init__(self, s): self._s = s

            def __truediv__(self, other):
                return _LoopingPath(f"{self._s}/{other}")

            def resolve(self):
                raise RuntimeError(f"Symlink loop from '{self._s}'")

        monkeypatch.setattr("logger_main.Path", _LoopingPath, raising=False)

        # If RuntimeError escaped the helper the await here would raise
        # and the test would fail loudly — the point of the fix.
        await daemon._attempt_usbdevfs_reset("/dev/ttyFAKE")

        assert daemon._usb_reset_count == 0
        assert daemon._last_usb_reset_at is None

    async def test_resolver_soft_returns_on_unparseable_busnum(
        self, daemon, monkeypatch, tmp_path,
    ):
        """A busnum file whose contents are not an integer (corrupted
        sysfs, kernel bug, race during enumeration) must log and
        return instead of raising.  ``int()`` on a non-numeric string
        raises ``ValueError``, which the helper already handles — this
        pins the invariant so a future refactor doesn't widen the
        except clause away."""
        import fcntl as _fcntl

        sys_root = tmp_path / "sys"
        usb_dev = sys_root / "devices" / "usbWEIRD"
        tty_leaf = usb_dev / "ttyWEIRD" / "tty" / "ttyWEIRD"
        tty_leaf.mkdir(parents=True)
        (usb_dev / "busnum").write_text("not-a-number\n")
        (usb_dev / "devnum").write_text("17\n")
        class_tty = sys_root / "class" / "tty"
        class_tty.mkdir(parents=True)
        (class_tty / "ttyWEIRD").symlink_to(tty_leaf)

        import pathlib
        real_path_cls = pathlib.Path

        def _fake_path(arg):
            s = str(arg)
            if s.startswith("/sys/class/tty"):
                return real_path_cls(str(sys_root) + s[4:])
            return real_path_cls(arg)

        monkeypatch.setattr("logger_main.Path", _fake_path, raising=False)

        # No ioctl must fire if the resolver bailed.
        ioctl_calls: list = []
        monkeypatch.setattr(
            _fcntl, "ioctl",
            lambda *a, **k: ioctl_calls.append(a),
        )
        monkeypatch.setattr(
            logger_main.os, "open",
            lambda *a, **k: pytest.fail("os.open should not be called"),
        )

        await daemon._attempt_usbdevfs_reset("/dev/ttyWEIRD")

        assert ioctl_calls == []
        assert daemon._usb_reset_count == 0

    async def test_resolver_soft_returns_on_non_usb_tty(
        self, daemon, monkeypatch, tmp_path,
    ):
        """A built-in UART (ttyS0, ttyAMA0, etc.) has no USB ancestor
        in sysfs — the walk from ``/sys/class/tty/<name>`` reaches
        the filesystem root without finding busnum+devnum.  Operators
        with a mixed-adapter host must not see the helper crash just
        because its string check matched a non-USB port name."""
        import fcntl as _fcntl

        # /sys/devices/platform/serial8250/ttyS0 — no busnum anywhere.
        sys_root = tmp_path / "sys"
        tty_leaf = (
            sys_root / "devices" / "platform" / "serial8250" / "ttyS0"
        )
        tty_leaf.mkdir(parents=True)
        class_tty = sys_root / "class" / "tty"
        class_tty.mkdir(parents=True)
        (class_tty / "ttyS0").symlink_to(tty_leaf)

        import pathlib
        real_path_cls = pathlib.Path

        def _fake_path(arg):
            s = str(arg)
            if s.startswith("/sys/class/tty"):
                return real_path_cls(str(sys_root) + s[4:])
            return real_path_cls(arg)

        monkeypatch.setattr("logger_main.Path", _fake_path, raising=False)

        ioctl_calls: list = []
        monkeypatch.setattr(
            _fcntl, "ioctl",
            lambda *a, **k: ioctl_calls.append(a),
        )
        monkeypatch.setattr(
            logger_main.os, "open",
            lambda *a, **k: pytest.fail("os.open should not be called"),
        )

        await daemon._attempt_usbdevfs_reset("/dev/ttyS0")

        assert ioctl_calls == []
        assert daemon._usb_reset_count == 0

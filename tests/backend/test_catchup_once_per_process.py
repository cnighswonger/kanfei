"""Regression test for #505 — DMPAFT catchup fires at most once per
process lifetime.

Before the fix, ``_bg_dmpaft_catchup`` ran on every connect (initial
plus every watchdog-forced reconnect), took ~77 s to walk a full
513-page archive on a Vantage over 19200 baud, and got its serial
port closed by the next 30 s poll-stall watchdog mid-page-read.
Every reconnect fired another catchup, holding the ``_io_lock`` past
the poll-stall threshold again — infinite loop, poller never runs,
no rows ever inserted.

The gate: ``LoggerDaemon._catchup_completed`` is set BEFORE the
service-function await, so a raised exception below still burns the
attempt. A successful catchup and a failed catchup are both terminal
for this process.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_daemon():
    """Build a LoggerDaemon with the wiring the test cares about.

    ``LoggerDaemon.__init__`` reads ``settings.db_path`` for the
    state-file path, which drags in the full config surface.  Bypass
    it via ``__new__`` (same pattern as
    ``test_firmware_status.py`` / ``test_console_location.py``) and
    hand-wire the fields ``_bg_dmpaft_catchup`` reads.
    """
    from logger_main import LoggerDaemon

    d = LoggerDaemon.__new__(LoggerDaemon)
    d.driver = MagicMock()
    # hasattr(drv, "async_dmpaft") must be True for the method to
    # reach the gate — otherwise the drv-check short-circuits before
    # ``_catchup_completed`` is set.
    d.driver.async_dmpaft = AsyncMock()
    d.relay_sender = MagicMock()
    d.relay_sender.push_backfill = AsyncMock()
    d._catchup_completed = False
    return d


def test_catchup_fires_exactly_once_on_success() -> None:
    d = _make_daemon()
    with patch(
        "logger_main.async_backfill_from_vantage",
        new=AsyncMock(return_value=(3, [{"timestamp": "2026-08-26T10:00:00", "outside_temp": 250}])),
    ) as backfill:
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))

    assert backfill.await_count == 1
    assert d._catchup_completed is True


def test_catchup_gate_burns_on_failure_too() -> None:
    """A failed first attempt still marks the process done — otherwise
    the loop we're fixing rearms on the next reconnect."""
    d = _make_daemon()
    with patch(
        "logger_main.async_backfill_from_vantage",
        new=AsyncMock(side_effect=RuntimeError("boom from driver")),
    ) as backfill:
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))
        # Second fire must NOT retry — the whole point of the gate.
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))

    assert backfill.await_count == 1
    assert d._catchup_completed is True


def test_catchup_gate_burns_on_service_return_empty() -> None:
    """The service function catches driver exceptions internally and
    returns ``(0, [])``.  The daemon-level gate still burns — the
    poll-stall lockup that motivated #505 happens BEFORE the service
    function returns, whether or not any rows made it through."""
    d = _make_daemon()
    with patch(
        "logger_main.async_backfill_from_vantage",
        new=AsyncMock(return_value=(0, [])),
    ) as backfill:
        for _ in range(4):
            asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))

    assert backfill.await_count == 1
    assert d._catchup_completed is True


def test_no_driver_no_gate_burn() -> None:
    """Guard: a call before the driver is wired must not consume the
    once-per-process budget.  Otherwise a startup race would silently
    disable catchup for the whole process life."""
    from logger_main import LoggerDaemon

    d = LoggerDaemon.__new__(LoggerDaemon)
    d.driver = None
    d._catchup_completed = False

    with patch(
        "logger_main.async_backfill_from_vantage",
        new=AsyncMock(),
    ) as backfill:
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))

    assert backfill.await_count == 0
    assert d._catchup_completed is False


def test_driver_missing_async_dmpaft_no_gate_burn() -> None:
    """Same as above for a LinkDriver / legacy path that doesn't have
    async_dmpaft — the call is a no-op AND leaves the gate un-burned."""
    from logger_main import LoggerDaemon

    d = LoggerDaemon.__new__(LoggerDaemon)
    d.driver = MagicMock(spec=[])  # spec=[] gives NO attributes
    d._catchup_completed = False

    with patch(
        "logger_main.async_backfill_from_vantage",
        new=AsyncMock(),
    ) as backfill:
        asyncio.run(d._bg_dmpaft_catchup(station_type_code=17))

    assert backfill.await_count == 0
    assert d._catchup_completed is False

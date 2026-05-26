"""Tests for the midnight rain rollover task in LoggerDaemon.

Covers two regressions identified in the kanfei issue tracker:

1. The loop body referenced ``self._running`` which was never initialised
   on ``LoggerDaemon``.  The task died on its first iteration with an
   ``AttributeError`` swallowed by asyncio, so the rollover had never
   actually fired on any deployment.  These tests assert the loop body
   survives at least one scheduled iteration without raising.

2. ``_do_midnight_rain_reset`` converted Davis click counts to inches via
   a hardcoded ``* 0.01``, ignoring ``rain_cal``.  PR #149 fixed the same
   formula in the poller but missed this path.  These tests assert the
   conversion now matches ``inches = clicks / rain_cal`` across the
   calibration values exercised in ``test_rain_unit_conversion.py``.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from logger_main import LoggerDaemon


@pytest.fixture(autouse=True)
def _clean_station_config():
    """Recreate the ``station_config`` table fresh for every test so each
    case starts without a stale ``rain_yesterday`` row."""
    Base.metadata.drop_all(bind=engine, tables=[StationConfigModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[StationConfigModel.__table__])
    yield
    db = SessionLocal()
    try:
        db.query(StationConfigModel).delete()
        db.commit()
    finally:
        db.close()


def _make_daemon_with_link(daily_clicks: int, rain_cal: int) -> LoggerDaemon:
    """Build a LoggerDaemon wired to a stub Davis LinkDriver.

    Only the surface that ``_do_midnight_rain_reset`` and
    ``_refresh_after_rain_clear`` touch is stubbed — everything else is
    left at the daemon's default state.
    """
    daemon = LoggerDaemon()

    link = MagicMock()
    link.connected = True
    link.calibration = SimpleNamespace(rain_cal=rain_cal)
    link.async_read_rain_daily = AsyncMock(return_value=daily_clicks)
    link.async_clear_rain_daily = AsyncMock(return_value=True)

    # ``_link`` is a property that does ``isinstance(self.driver, LinkDriver)``
    # — patching the attribute on the class would be invasive, so we patch
    # the property's underlying logic by setting ``driver`` to the link and
    # overriding the property at instance scope via __dict__-bypass.
    daemon.driver = link
    daemon.__class__._link = property(lambda self: link)  # type: ignore[assignment]

    # Stub the post-clear refresh so the test doesn't need a real poller.
    async def _noop():
        return None

    daemon._refresh_after_rain_clear = _noop  # type: ignore[assignment]
    daemon.poller = SimpleNamespace(rain_yesterday=0.0)

    return daemon


def _restore_link_property():
    """Undo the per-test monkey-patch of the ``_link`` property."""
    from app.protocol.link_driver import LinkDriver

    def _link(self):
        return self.driver if isinstance(self.driver, LinkDriver) else None

    LoggerDaemon._link = property(_link)  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def _restore_link_after_each_test():
    yield
    _restore_link_property()


class TestRainCalConversion:
    """``_do_midnight_rain_reset`` must persist ``daily_inches = clicks / rain_cal``."""

    @pytest.mark.asyncio
    async def test_default_rain_cal_100(self):
        # 100 clicks at rain_cal=100 = 1.00 inch.  This is the Davis default
        # and the only setting where the old ``* 0.01`` formula was correct.
        daemon = _make_daemon_with_link(daily_clicks=100, rain_cal=100)
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert row is not None
            assert float(row.value) == pytest.approx(1.00)
        finally:
            db.close()

        assert daemon.poller.rain_yesterday == pytest.approx(1.00)

    @pytest.mark.asyncio
    async def test_workaround_rain_cal_254(self):
        # 254 clicks at rain_cal=254 = 1.00 inch.  The old hardcoded ``* 0.01``
        # would have reported 2.54 inches here — the 2.54× over-report
        # documented in PR #149 for workaround users.
        daemon = _make_daemon_with_link(daily_clicks=254, rain_cal=254)
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(1.00)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_metric_bucket_rain_cal_127(self):
        # 127 clicks at rain_cal=127 (0.2 mm bucket) = 1.00 inch = 25.4 mm.
        daemon = _make_daemon_with_link(daily_clicks=127, rain_cal=127)
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(1.00)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_zero_clicks_records_zero(self):
        daemon = _make_daemon_with_link(daily_clicks=0, rain_cal=100)
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == 0.0
        finally:
            db.close()


class TestLoopSurvivesFirstIteration:
    """The ``_midnight_rain_reset_loop`` must not raise ``AttributeError``
    on entry — that was the regression that left rollover dead since the
    initial commit."""

    @pytest.mark.asyncio
    async def test_loop_runs_and_cancels_cleanly(self, monkeypatch):
        daemon = _make_daemon_with_link(daily_clicks=42, rain_cal=100)

        # Force the loop to wake immediately by making ``next_midnight`` ~0s
        # away.  Patch ``_get_station_timezone`` to return UTC and stub
        # ``_do_midnight_rain_reset`` so the test stays in pure-Python land.
        monkeypatch.setattr(
            daemon, "_get_station_timezone", lambda: timezone.utc,
        )

        # Make ``datetime.now(tz)`` return one second before UTC midnight so
        # the loop's ``asyncio.sleep`` resolves almost instantly.
        class _FakeDT:
            @classmethod
            def now(cls, tz=None):
                # 23:59:59 UTC on an arbitrary date.
                return datetime(2026, 5, 26, 23, 59, 59, tzinfo=tz)

        # Patch the module-level ``datetime`` used by the loop.
        import logger_main as lm
        monkeypatch.setattr(lm, "datetime", _FakeDT)

        # Record whether the body executed; an AttributeError would prevent
        # this from ever being called.
        body_calls: list[int] = []

        async def _record_body():
            body_calls.append(1)

        daemon._do_midnight_rain_reset = _record_body  # type: ignore[assignment]

        task = asyncio.create_task(daemon._midnight_rain_reset_loop())

        # Give the loop enough time to wake, run the body once, and start
        # the next sleep; then cancel.
        try:
            await asyncio.wait_for(
                asyncio.shield(_wait_until(lambda: len(body_calls) >= 1)),
                timeout=5.0,
            )
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert body_calls, "loop body never ran (regression: self._running)"

    @pytest.mark.asyncio
    async def test_cancellation_during_sleep_exits_cleanly(self, monkeypatch):
        """When the daemon is shutting down (``_teardown_driver`` cancels
        ``self._midnight_task``), the loop's ``except CancelledError: break``
        clause should catch the cancel and let the coroutine return
        normally — no unhandled exception on the task, no ``AttributeError``
        from a missing ``self._running``."""
        daemon = _make_daemon_with_link(daily_clicks=0, rain_cal=100)
        monkeypatch.setattr(
            daemon, "_get_station_timezone", lambda: timezone.utc,
        )

        task = asyncio.create_task(daemon._midnight_rain_reset_loop())
        await asyncio.sleep(0.05)  # let it enter the long sleep until next midnight
        task.cancel()
        await task  # must NOT re-raise CancelledError — the loop catches it
        assert task.exception() is None


async def _wait_until(predicate, interval: float = 0.01):
    while not predicate():
        await asyncio.sleep(interval)

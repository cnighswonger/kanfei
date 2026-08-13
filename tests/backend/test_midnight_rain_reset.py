"""Tests for the midnight rain rollover task in LoggerDaemon.

The rollover has two responsibilities:

1. **Snapshot yesterday**: read today's terminal ``rain_total`` and persist
   it as ``station_config.rain_yesterday``.  This is driver-agnostic — the
   value comes from the latest pre-midnight ``sensor_readings`` row that
   every driver's poll path writes to.  See #171.

2. **Clear hardware (Davis only)**: on ``LinkDriver`` stations the daily
   counter is a hardware register that must be zeroed via
   ``async_clear_rain_daily`` or it keeps accumulating.  Non-Davis drivers
   (Tempest et al.) self-zero their internal state on the first
   post-midnight poll, so the daemon does nothing hardware-side for them.

Order matters on Davis: clear FIRST, persist only if the clear succeeds.
Otherwise tomorrow's midnight reads an un-cleared register (today's total
+ tomorrow's rainfall) and rolls that pile into ``rain_yesterday``.

Regression history covered here:

- #170: ``_midnight_rain_reset_loop`` referenced a nonexistent
  ``self._running``, so the task died on its first iteration; the
  ``TestLoopSurvivesFirstIteration`` class locks that.
- #173: yesterday was committed BEFORE the hardware clear; #173 flipped
  the order, and the ``TestClearMustSucceedBeforeYesterdayCommit`` class
  keeps the invariant welded.
- #171: rollover was Davis-only because the whole method returned early
  when ``self._link`` was None; ``TestDriverAgnosticSnapshot`` covers the
  driver-agnostic DB path that replaced it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.models.station_config import StationConfigModel
from logger_main import LoggerDaemon


@pytest.fixture(autouse=True)
def _clean_tables():
    """Recreate the tables the rollover touches for every test so each case
    starts with an empty ``station_config`` (no ``rain_yesterday`` row) and
    an empty ``sensor_readings`` (no historical rain readings)."""
    tables = [StationConfigModel.__table__, SensorReadingModel.__table__]
    Base.metadata.drop_all(bind=engine, tables=tables)
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    db = SessionLocal()
    try:
        db.query(StationConfigModel).delete()
        db.query(SensorReadingModel).delete()
        db.commit()
    finally:
        db.close()


def _seed_reading_before_midnight(rain_total_tenths_mm: int | None,
                                   station_type: int = 16,
                                   minutes_ago: int = 5) -> None:
    """Seed a single ``sensor_readings`` row at ``minutes_ago`` before the
    local midnight the rollover will pick as its cutoff.

    The rollover reads ``self._get_station_timezone()`` which falls back to
    the system local tz when no config row says otherwise.  The tests use
    the same fallback, so both sides agree on which midnight to compare
    against.
    """
    tz = datetime.now().astimezone().tzinfo
    today_local_midnight_utc = (
        datetime.now(tz)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    ts = today_local_midnight_utc - timedelta(minutes=minutes_ago)
    db = SessionLocal()
    try:
        db.add(SensorReadingModel(
            timestamp=ts,
            station_type=station_type,
            rain_total=rain_total_tenths_mm,
        ))
        db.commit()
    finally:
        db.close()


def _make_daemon_with_link() -> LoggerDaemon:
    """Build a LoggerDaemon wired to a stub Davis LinkDriver.

    Only the surface that ``_do_midnight_rain_reset`` and
    ``_refresh_after_rain_clear`` touch is stubbed.  The daily-rain value
    is no longer read via ``async_read_rain_daily`` (it comes from the DB
    now), so the mock doesn't need to seed a click count.
    """
    daemon = LoggerDaemon()

    link = MagicMock()
    link.connected = True
    link.async_clear_rain_daily = AsyncMock(return_value=True)

    # ``_link`` is a property that does ``isinstance(self.driver, LinkDriver)``
    # — patching that property lets the tests avoid importing the real
    # LinkDriver just to satisfy the isinstance check.
    daemon.driver = link
    daemon.__class__._link = property(lambda self: link)  # type: ignore[assignment]

    async def _noop():
        return None

    daemon._refresh_after_rain_clear = _noop  # type: ignore[assignment]
    daemon.poller = SimpleNamespace(rain_yesterday=0.0)

    return daemon


def _make_daemon_non_davis() -> LoggerDaemon:
    """Build a LoggerDaemon that presents as a non-Davis driver
    (``self._link`` returns None).  Used for the driver-agnostic path."""
    daemon = LoggerDaemon()
    daemon.driver = SimpleNamespace(connected=True)
    daemon.__class__._link = property(lambda self: None)  # type: ignore[assignment]

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


# --- Conversion of the DB-stored value to inches ---
#
# ``sensor_readings.rain_total`` is stored in tenths of a millimetre
# (see SENSOR_BOUNDS in app/models/sensor_meta.py).  The rollover
# converts to inches via ``mm / 25.4`` — the rain_cal-aware conversion
# already happened when the poller wrote the row, so nothing calibration-
# specific belongs in the rollover itself anymore.

class TestSnapshotFromDatabase:
    """The rollover value must come from ``sensor_readings.rain_total`` of
    the latest pre-midnight row, converted from tenths-mm to inches."""

    @pytest.mark.asyncio
    async def test_zero_reading_records_zero(self):
        _seed_reading_before_midnight(rain_total_tenths_mm=0)
        daemon = _make_daemon_with_link()
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == 0.0
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_one_inch_reading(self):
        # 254 tenths-mm = 25.4 mm = 1.00 inch
        _seed_reading_before_midnight(rain_total_tenths_mm=254)
        daemon = _make_daemon_with_link()
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(1.00)
        finally:
            db.close()
        assert daemon.poller.rain_yesterday == pytest.approx(1.00)

    @pytest.mark.asyncio
    async def test_multiple_readings_uses_latest_before_midnight(self):
        """Seed three readings over the last hour; the latest one is what
        gets snapshotted."""
        tz = datetime.now().astimezone().tzinfo
        today_local_midnight_utc = (
            datetime.now(tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        db = SessionLocal()
        try:
            for minutes_ago, value in [(60, 100), (30, 200), (5, 305)]:
                db.add(SensorReadingModel(
                    timestamp=today_local_midnight_utc - timedelta(minutes=minutes_ago),
                    station_type=16,
                    rain_total=value,
                ))
            db.commit()
        finally:
            db.close()

        daemon = _make_daemon_with_link()
        await daemon._do_midnight_rain_reset()

        # 305 tenths-mm = 30.5 mm = 1.20 inches (rounded to 2 dp)
        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(1.20)
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_null_rain_total_falls_back_to_zero(self):
        """A row that exists but has ``rain_total = NULL`` (station with no
        rain gauge, or a driver that hasn't populated the column) rolls to
        0.0 rather than crashing."""
        _seed_reading_before_midnight(rain_total_tenths_mm=None)
        daemon = _make_daemon_with_link()
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == 0.0
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_no_rows_falls_back_to_zero(self):
        """First day online, extended outage, freshly-purged DB — no
        pre-midnight rows.  Roll to 0.0 rather than skipping."""
        daemon = _make_daemon_with_link()
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == 0.0
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_post_midnight_row_is_not_snapshotted(self):
        """A reading that landed AFTER local midnight belongs to today, not
        yesterday.  The query must exclude it even when it's the most
        recent row overall.

        This is the specific race the pre-midnight filter guards against:
        if the first post-midnight poll lands milliseconds before the
        rollover task wakes, its zeroed rain_total would otherwise get
        snapshotted as yesterday's terminal value.
        """
        tz = datetime.now().astimezone().tzinfo
        today_local_midnight_utc = (
            datetime.now(tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        db = SessionLocal()
        try:
            # Yesterday's final value (5 min before midnight)
            db.add(SensorReadingModel(
                timestamp=today_local_midnight_utc - timedelta(minutes=5),
                station_type=16,
                rain_total=250,  # 25 mm ≈ 0.98 in
            ))
            # Today's first post-midnight poll, already zeroed by the driver
            db.add(SensorReadingModel(
                timestamp=today_local_midnight_utc + timedelta(seconds=30),
                station_type=16,
                rain_total=0,
            ))
            db.commit()
        finally:
            db.close()

        daemon = _make_daemon_with_link()
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(0.98), (
                "post-midnight zero row leaked into yesterday's snapshot"
            )
        finally:
            db.close()


class TestClearMustSucceedBeforeYesterdayCommit:
    """The Davis path clears the hardware register first; if the clear
    fails or raises, yesterday must NOT be persisted or the next midnight
    will double-count.  Non-Davis path skips this whole block (no hardware
    to clear) — see ``TestDriverAgnosticSnapshot``."""

    @pytest.mark.asyncio
    async def test_clear_returning_false_does_not_persist_yesterday(self):
        _seed_reading_before_midnight(rain_total_tenths_mm=127)  # 0.5 inch-ish
        daemon = _make_daemon_with_link()
        daemon.driver.async_clear_rain_daily = AsyncMock(return_value=False)

        # Seed an existing rain_yesterday row so we can verify it is NOT
        # overwritten when the clear fails.
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="rain_yesterday",
                value="0.99",
                updated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
            ))
            db.commit()
        finally:
            db.close()

        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(0.99), \
                "yesterday was overwritten despite hardware clear failure"
        finally:
            db.close()

        assert daemon.poller.rain_yesterday == 0.0

    @pytest.mark.asyncio
    async def test_clear_raising_does_not_persist_yesterday(self):
        _seed_reading_before_midnight(rain_total_tenths_mm=127)
        daemon = _make_daemon_with_link()
        daemon.driver.async_clear_rain_daily = AsyncMock(
            side_effect=RuntimeError("serial timeout"),
        )
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="rain_yesterday",
                value="0.42",
                updated_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
            ))
            db.commit()
        finally:
            db.close()

        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert float(row.value) == pytest.approx(0.42)
        finally:
            db.close()
        assert daemon.poller.rain_yesterday == 0.0

    @pytest.mark.asyncio
    async def test_clear_called_before_persist_on_happy_path(self):
        """Lock the ordering invariant: clear runs first, persist runs after."""
        _seed_reading_before_midnight(rain_total_tenths_mm=254)
        daemon = _make_daemon_with_link()

        calls: list[str] = []

        async def _record_clear():
            calls.append("clear")
            return True

        daemon.driver.async_clear_rain_daily = _record_clear

        orig_session = SessionLocal

        class _TrackingSession:
            def __init__(self):
                self._s = orig_session()

            def __getattr__(self, name):
                if name == "commit":
                    def commit():
                        # Only record the commit that persists yesterday
                        # (later than the read-only DB query).
                        calls.append("persist")
                        return self._s.commit()
                    return commit
                return getattr(self._s, name)

        import logger_main as lm
        original = lm.SessionLocal
        lm.SessionLocal = _TrackingSession
        try:
            await daemon._do_midnight_rain_reset()
        finally:
            lm.SessionLocal = original

        assert calls == ["clear", "persist"], (
            f"clear must precede persist, got {calls}"
        )


class TestDriverAgnosticSnapshot:
    """Non-Davis drivers used to be silent no-ops (#171).  They must now
    persist yesterday from the DB just like Davis, without touching any
    hardware-clear path."""

    @pytest.mark.asyncio
    async def test_non_davis_persists_yesterday_from_db(self):
        _seed_reading_before_midnight(rain_total_tenths_mm=254)
        daemon = _make_daemon_non_davis()
        await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert row is not None, (
                "non-Davis rollover must persist yesterday (#171 fix)"
            )
            assert float(row.value) == pytest.approx(1.00)
        finally:
            db.close()
        assert daemon.poller.rain_yesterday == pytest.approx(1.00)

    @pytest.mark.asyncio
    async def test_non_davis_does_not_warn_about_hardware(self, caplog):
        """A non-Davis rollover must not emit any misleading 'station not
        connected' or 'hardware clear failed' log lines — there is no
        hardware to clear on Tempest / Ambient / etc."""
        _seed_reading_before_midnight(rain_total_tenths_mm=0)
        daemon = _make_daemon_non_davis()

        import logging
        with caplog.at_level(logging.WARNING, logger="davis.logger"):
            await daemon._do_midnight_rain_reset()

        warn = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and "Midnight rain reset" in r.message
        ]
        assert warn == [], (
            f"non-Davis rollover should not warn about hardware, got: "
            f"{[r.message for r in warn]}"
        )

    @pytest.mark.asyncio
    async def test_non_davis_does_not_call_hardware_refresh(self):
        """``_refresh_after_rain_clear`` exists to reset the Davis poller's
        cached ``_last_rain_daily`` after a hardware clear so the next poll's
        rain_rate doesn't see a phantom drop.  Non-Davis drivers manage
        their own daily state internally and don't need this refresh."""
        _seed_reading_before_midnight(rain_total_tenths_mm=254)
        daemon = _make_daemon_non_davis()

        called = []

        async def _tracking_refresh():
            called.append(1)

        daemon._refresh_after_rain_clear = _tracking_refresh
        await daemon._do_midnight_rain_reset()

        assert called == [], (
            "refresh_after_rain_clear should not be called on non-Davis "
            "(no hardware clear happened)"
        )

    @pytest.mark.asyncio
    async def test_no_driver_at_all_skips_with_warning(self, caplog):
        """If ``self.driver`` is None (daemon starting up, connection lost
        entirely), skip cleanly with a single warning — don't try to persist
        anything."""
        daemon = LoggerDaemon()
        daemon.driver = None

        import logging
        with caplog.at_level(logging.WARNING, logger="davis.logger"):
            await daemon._do_midnight_rain_reset()

        db = SessionLocal()
        try:
            row = db.query(StationConfigModel).filter_by(key="rain_yesterday").first()
            assert row is None
        finally:
            db.close()

        warn = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and "no driver" in r.message
        ]
        assert len(warn) == 1


class TestLoopSurvivesFirstIteration:
    """The ``_midnight_rain_reset_loop`` must not raise ``AttributeError``
    on entry — that was the #170 regression that left rollover dead since
    the initial commit."""

    @pytest.mark.asyncio
    async def test_loop_runs_and_cancels_cleanly(self, monkeypatch):
        _seed_reading_before_midnight(rain_total_tenths_mm=0)
        daemon = _make_daemon_with_link()

        monkeypatch.setattr(
            daemon, "_get_station_timezone", lambda: timezone.utc,
        )

        class _FakeDT:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 5, 26, 23, 59, 59, tzinfo=tz)

        import logger_main as lm
        monkeypatch.setattr(lm, "datetime", _FakeDT)

        body_calls: list[int] = []

        async def _record_body():
            body_calls.append(1)

        daemon._do_midnight_rain_reset = _record_body  # type: ignore[assignment]

        task = asyncio.create_task(daemon._midnight_rain_reset_loop())

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
        _seed_reading_before_midnight(rain_total_tenths_mm=0)
        daemon = _make_daemon_with_link()
        monkeypatch.setattr(
            daemon, "_get_station_timezone", lambda: timezone.utc,
        )

        task = asyncio.create_task(daemon._midnight_rain_reset_loop())
        await asyncio.sleep(0.05)
        task.cancel()
        await task
        assert task.exception() is None


async def _wait_until(predicate, interval: float = 0.01):
    while not predicate():
        await asyncio.sleep(interval)

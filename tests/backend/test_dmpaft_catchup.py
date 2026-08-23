"""DMPAFT catchup — sub-issue #477 of umbrella #472.

Pins the reconnect-time console-archive backfill:

- Records land in ``sensor_readings`` at the timestamp shape live
  polls use (naive-UTC), so ``/api/history`` charts them continuously
  with the live samples on either side of the gap.
- Duplicate-safe: rerunning against the same DB state inserts zero.
- Empty DB uses the fresh-install horizon, not "beginning of time".
- Cap at MAX_BACKFILL_RECORDS defends against a driver bug returning
  the whole world.
- Failure inside ``async_dmpaft`` is a warning, not a raise —
  callers run this as a background task and must never crash the
  reconnect path.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.database import Base, engine, SessionLocal
from app.models.sensor_reading import SensorReadingModel
from app.protocol.vantage.archive import VantageArchiveRecord
from app.services.dmpaft_catchup import (
    FRESH_INSTALL_HORIZON,
    MAX_BACKFILL_RECORDS,
    async_backfill_from_vantage,
    _floor_timestamp,
    _to_utc_naive,
)

STATION_TYPE_VUE = 17


@pytest.fixture(autouse=True)
def _clean_sensor_readings():
    tables = [SensorReadingModel.__table__]
    Base.metadata.drop_all(bind=engine, tables=tables)
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    db = SessionLocal()
    try:
        db.query(SensorReadingModel).delete()
        db.commit()
    finally:
        db.close()


class _FakeVantageDriver:
    """Structural stub for ``async_dmpaft``.

    ``asked_after`` records the timestamp DMPAFT was called with — the
    tests use it to prove ``_floor_timestamp`` picked the right anchor.
    """

    def __init__(self, records=None, raise_exc: Exception | None = None):
        self._records = records or []
        self._raise = raise_exc
        self.asked_after: datetime | None = None
        self.call_count = 0

    async def async_dmpaft(self, after: datetime):
        self.call_count += 1
        self.asked_after = after
        if self._raise is not None:
            raise self._raise
        return list(self._records)


def _mk_record(minutes_ago: int) -> VantageArchiveRecord:
    """One well-formed archive record whose local-time stamp is
    ``minutes_ago`` minutes before now (local)."""
    ts = datetime.now().replace(second=0, microsecond=0) - timedelta(
        minutes=minutes_ago,
    )
    return VantageArchiveRecord(
        timestamp=ts,
        outside_temp_avg=22.5,
        outside_humidity=60,
        barometer=1013.2,
        wind_speed_avg=2.5,
        wind_dir_prevailing=180,
        solar_radiation=500,
    )


class TestFreshInstall:
    pytestmark = pytest.mark.asyncio

    async def test_uses_horizon_when_no_live_samples(self):
        """DB is empty; catchup must ask the console for a bounded
        window, not "since epoch" — a 30-min-interval station would
        otherwise stream a decade of records."""
        drv = _FakeVantageDriver(records=[_mk_record(30)])
        n = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert n == 1
        assert drv.asked_after is not None
        expected_floor = datetime.now() - FRESH_INSTALL_HORIZON
        # Some slack for the wall-clock delta between the two now()
        # calls; the point is the horizon shape, not exact seconds.
        assert abs(
            (drv.asked_after - expected_floor).total_seconds(),
        ) < 60


class TestInsertion:
    pytestmark = pytest.mark.asyncio

    async def test_records_land_in_sensor_readings(self):
        drv = _FakeVantageDriver(records=[
            _mk_record(30), _mk_record(20), _mk_record(10),
        ])
        n = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert n == 3
        db = SessionLocal()
        try:
            count = db.query(SensorReadingModel).count()
            assert count == 3
        finally:
            db.close()

    async def test_scales_temperature_to_tenths_c_like_live_poller(self):
        """Backfilled rows are charted alongside live rows.  If the
        scaling differs, the chart doubles or halves across the
        gap boundary."""
        drv = _FakeVantageDriver(records=[_mk_record(10)])
        await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).one()
            # VantageArchiveRecord.outside_temp_avg=22.5 → 225 tenths.
            assert row.outside_temp == 225
            # Wind 2.5 m/s → 25 tenths.
            assert row.wind_speed == 25
            # Barometer 1013.2 hPa → 10132 tenths hPa.
            assert row.barometer == 10132
        finally:
            db.close()

    async def test_computes_dew_point_and_heat_index_like_live_poller(self):
        """A backfilled row that omits derived values would show a
        broken derived-conditions trace across the gap.  Same
        calculation the poller runs; result is stored in tenths."""
        drv = _FakeVantageDriver(records=[_mk_record(10)])
        await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).one()
            assert row.dew_point is not None
            assert row.heat_index is not None
        finally:
            db.close()

    async def test_flags_source_in_extra_json(self):
        """Debuggability: a chart oddity should be attributable to
        the catchup path vs a live sample without diffing timestamps."""
        drv = _FakeVantageDriver(records=[_mk_record(10)])
        await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        db = SessionLocal()
        try:
            row = db.query(SensorReadingModel).one()
            assert row.extra_json is not None
            assert "vantage_dmpaft" in row.extra_json
        finally:
            db.close()


class TestIdempotence:
    pytestmark = pytest.mark.asyncio

    async def test_second_run_inserts_zero_new_rows(self):
        """The exact "safe to call redundantly" claim in the module
        docstring — the watchdog may fire this on top of a prior
        catchup while the /api/health monitor is still flapping."""
        records = [_mk_record(30), _mk_record(20)]
        drv = _FakeVantageDriver(records=records)
        first = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert first == 2
        second = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert second == 0
        db = SessionLocal()
        try:
            assert db.query(SensorReadingModel).count() == 2
        finally:
            db.close()

    async def test_asks_after_newest_live_sample_when_present(self):
        """Once live samples exist, we anchor the ``after`` at the
        newest of them, not the fresh-install horizon.  This is
        what makes the tight-reconnect case cheap."""
        # Seed a "live" row a few minutes ago.
        seed_utc = datetime.now(timezone.utc).replace(
            second=0, microsecond=0,
        ) - timedelta(minutes=5)
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=seed_utc.replace(tzinfo=None),
                station_type=STATION_TYPE_VUE,
                outside_temp=200,
            ))
            db.commit()
        finally:
            db.close()

        drv = _FakeVantageDriver(records=[_mk_record(2)])
        await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert drv.asked_after is not None
        # DMPAFT wants local time; we seeded UTC, so convert.  The
        # anchor is minutes-ago, not hours-ago (fresh-install horizon
        # is 3 days).
        assert (
            datetime.now() - drv.asked_after
        ).total_seconds() < 3600  # < 1h


class TestGuards:
    pytestmark = pytest.mark.asyncio

    async def test_caps_at_max_backfill_records(self):
        """A driver bug returning the whole ring (or worse) must not
        translate into an unbounded write burst."""
        drv = _FakeVantageDriver(
            records=[_mk_record(m) for m in range(MAX_BACKFILL_RECORDS + 50)],
        )
        n = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert n == MAX_BACKFILL_RECORDS

    async def test_dmpaft_raise_becomes_warning_not_crash(self):
        """Called from a background task in `_bg_dmpaft_catchup`; a
        raise here would take down the reconnect path.  Caller
        expects a return value it can log."""
        drv = _FakeVantageDriver(raise_exc=ConnectionError("wire ate it"))
        n = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert n == 0
        db = SessionLocal()
        try:
            assert db.query(SensorReadingModel).count() == 0
        finally:
            db.close()

    async def test_empty_result_is_zero_not_error(self):
        drv = _FakeVantageDriver(records=[])
        n = await async_backfill_from_vantage(drv, STATION_TYPE_VUE)
        assert n == 0
        assert drv.call_count == 1


class TestTimestampConversion:
    def test_naive_local_round_trips_to_naive_utc(self):
        """The convention that live rows and backfill rows share:
        naive-UTC in the DB, local-from-console in the wire read.
        Getting this wrong offsets the whole gap on the chart by
        the local UTC offset."""
        now_local = datetime.now().replace(microsecond=0)
        utc = _to_utc_naive(now_local)
        # Reversing via wall-clock delta should equal the local
        # zone's UTC offset.
        aware_local = datetime.now().astimezone()
        expected_offset = aware_local.utcoffset() or timedelta(0)
        assert now_local - utc == expected_offset

    def test_floor_uses_local_zone_representation(self):
        """DMPAFT compares against the console's local clock; the
        floor must be a naive local datetime, not naive UTC."""
        seed_utc = datetime.now(timezone.utc).replace(
            microsecond=0,
        ) - timedelta(hours=1)
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=seed_utc.replace(tzinfo=None),
                station_type=STATION_TYPE_VUE,
            ))
            db.commit()
        finally:
            db.close()

        floor = _floor_timestamp()
        # Naive.
        assert floor.tzinfo is None
        # Recognisable as an hour ago in LOCAL time; if the code
        # stored naive-UTC-shape instead, this delta would equal the
        # UTC offset plus 1 hour.
        aware_now_local = datetime.now().astimezone().replace(tzinfo=None)
        delta = aware_now_local - floor
        assert timedelta(minutes=55) <= delta <= timedelta(minutes=65)

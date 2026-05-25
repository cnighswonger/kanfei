"""Tests for the daily-extremes aggregate query.

Focus: the per-extreme ``at`` ISO timestamp added so the dashboard can
show *when* today's peak occurred next to the value (issue follow-up to
the test-user wind-peak-timestamp request).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.protocol.constants import StationModel
from app.services.daily_extremes import get_daily_extremes


@pytest.fixture
def fresh_readings():
    Base.metadata.drop_all(bind=engine, tables=[SensorReadingModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[SensorReadingModel.__table__])
    yield
    db = SessionLocal()
    try:
        db.query(SensorReadingModel).delete()
        db.commit()
    finally:
        db.close()


def _midnight_utc() -> datetime:
    now = datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _add(db, ts, **cols):
    db.add(SensorReadingModel(
        timestamp=ts,
        station_type=int(StationModel.MONITOR.value),
        **cols,
    ))


class TestAtTimestamp:

    def test_each_extreme_carries_iso_z_timestamp(self, fresh_readings):
        midnight = _midnight_utc()
        db = SessionLocal()
        try:
            # Single sample at 03:00 covering every aggregated column.
            ts = midnight + timedelta(hours=3)
            _add(db, ts,
                 outside_temp=720, inside_temp=680,
                 outside_humidity=50, inside_humidity=40,
                 wind_speed=100, barometer=29920, rain_rate=30)
            db.commit()
            extremes = get_daily_extremes(db)
        finally:
            db.close()

        assert extremes is not None
        for key in (
            "outside_temp_hi", "outside_temp_lo",
            "inside_temp_hi", "inside_temp_lo",
            "wind_speed_hi",
            "barometer_hi", "barometer_lo",
            "humidity_hi", "humidity_lo",
            "rain_rate_hi",
            "inside_humidity_hi", "inside_humidity_lo",
        ):
            entry = extremes[key]
            assert entry is not None, f"{key} missing"
            assert "value" in entry and "unit" in entry and "at" in entry
            assert isinstance(entry["at"], str)
            assert entry["at"].endswith("Z"), f"{key}: {entry['at']!r} should end with Z"

    def test_tied_maximum_returns_earliest_timestamp(self, fresh_readings):
        midnight = _midnight_utc()
        db = SessionLocal()
        try:
            early = midnight + timedelta(hours=2)
            late = midnight + timedelta(hours=8)
            # Both rows hit the same peak — earliest wins.
            _add(db, early, outside_temp=850)
            _add(db, late, outside_temp=850)
            db.commit()
            extremes = get_daily_extremes(db)
        finally:
            db.close()

        assert extremes is not None
        at = extremes["outside_temp_hi"]["at"]
        assert at == early.isoformat().replace("+00:00", "Z")

    def test_returns_none_when_no_rows_today(self, fresh_readings):
        db = SessionLocal()
        try:
            extremes = get_daily_extremes(db)
        finally:
            db.close()
        assert extremes is None

    def test_rows_before_midnight_are_excluded(self, fresh_readings):
        midnight = _midnight_utc()
        db = SessionLocal()
        try:
            # 23:59 yesterday-UTC — outside today's window.
            _add(db, midnight - timedelta(minutes=1), outside_temp=999)
            # 00:01 today — inside the window.
            _add(db, midnight + timedelta(minutes=1), outside_temp=700)
            db.commit()
            extremes = get_daily_extremes(db)
        finally:
            db.close()

        assert extremes is not None
        # Yesterday's 999 must not have leaked in.
        assert extremes["outside_temp_hi"]["value"] is not None
        assert extremes["outside_temp_hi"]["at"] is not None
        assert "999" not in str(extremes["outside_temp_hi"]["value"])

    def test_null_column_yields_null_extreme(self, fresh_readings):
        # Only outside_temp populated — rain_rate / barometer extremes
        # should come back as None entries, not raise.
        midnight = _midnight_utc()
        db = SessionLocal()
        try:
            _add(db, midnight + timedelta(hours=1), outside_temp=700)
            db.commit()
            extremes = get_daily_extremes(db)
        finally:
            db.close()

        assert extremes is not None
        assert extremes["outside_temp_hi"] is not None
        assert extremes["outside_temp_hi"]["at"] is not None
        # Columns with no non-null rows -> None entries.
        assert extremes["rain_rate_hi"] is None
        assert extremes["barometer_hi"] is None

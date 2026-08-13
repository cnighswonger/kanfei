"""Daily cumulative solar radiation integration.

Trapezoid-integrates ``sensor_readings.solar_radiation`` (W/m²) samples
since local midnight and returns the accumulated energy in J/m². The
integration is what a solar-panel or agricultural user reads as
'today's solar energy so far.'
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.models.station_config import StationConfigModel
from app.services.solar_energy import (
    compute_daily_solar_energy_j_per_m2,
    joules_to_display_unit,
)


@pytest.fixture(autouse=True)
def _clean_tables():
    tables = [SensorReadingModel.__table__, StationConfigModel.__table__]
    Base.metadata.drop_all(bind=engine, tables=tables)
    Base.metadata.create_all(bind=engine, tables=tables)
    yield
    db = SessionLocal()
    try:
        db.query(SensorReadingModel).delete()
        db.query(StationConfigModel).delete()
        db.commit()
    finally:
        db.close()


def _seed_today(samples: list[tuple[int, int]]) -> None:
    """Seed samples for today's local day.

    Each tuple is (minutes_after_local_midnight, solar_radiation_w_per_m2).
    """
    tz = datetime.now().astimezone().tzinfo
    today_local_midnight_utc_naive = (
        datetime.now(tz)
        .replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    db = SessionLocal()
    try:
        for minutes_after, flux in samples:
            db.add(SensorReadingModel(
                timestamp=today_local_midnight_utc_naive + timedelta(minutes=minutes_after),
                station_type=16,
                solar_radiation=flux,
            ))
        db.commit()
    finally:
        db.close()


class TestTrapezoidIntegration:
    """Verify the trapezoid maths on hand-computable cases."""

    def test_no_samples_returns_none(self):
        db = SessionLocal()
        try:
            assert compute_daily_solar_energy_j_per_m2(db) is None
        finally:
            db.close()

    def test_single_sample_returns_none(self):
        """One sample gives no interval to integrate over."""
        _seed_today([(600, 500)])  # 10am, 500 W/m²
        db = SessionLocal()
        try:
            assert compute_daily_solar_energy_j_per_m2(db) is None
        finally:
            db.close()

    def test_two_samples_constant_flux(self):
        """500 W/m² held for 1 hour → 500 W/m² * 3600s = 1_800_000 J/m²
        = 1.8 MJ/m²."""
        _seed_today([(600, 500), (660, 500)])
        db = SessionLocal()
        try:
            energy = compute_daily_solar_energy_j_per_m2(db)
            assert energy == pytest.approx(500 * 3600, abs=1)
        finally:
            db.close()

    def test_ramp_up_uses_average(self):
        """Trapezoid between (t=0s, 0 W/m²) and (t=3600s, 1000 W/m²) is
        the average flux (500) times the interval (3600s) = 1_800_000 J/m²."""
        _seed_today([(0, 0), (60, 1000)])
        db = SessionLocal()
        try:
            energy = compute_daily_solar_energy_j_per_m2(db)
            assert energy == pytest.approx(500 * 3600, abs=1)
        finally:
            db.close()

    def test_null_solar_rows_excluded(self):
        """Rows with solar_radiation NULL (station has no sensor at that
        moment) don't count. Two non-null samples still integrate."""
        _seed_today([(600, 500), (660, 500)])
        # Additional null row shouldn't crash or contribute
        tz = datetime.now().astimezone().tzinfo
        today_local_midnight_utc_naive = (
            datetime.now(tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=today_local_midnight_utc_naive + timedelta(minutes=630),
                station_type=16,
                solar_radiation=None,
            ))
            db.commit()
            energy = compute_daily_solar_energy_j_per_m2(db)
            # Should still equal the 500 W/m² * 3600s result — null row
            # excluded by the query.
            assert energy == pytest.approx(500 * 3600, abs=1)
        finally:
            db.close()

    def test_pre_midnight_rows_not_included(self):
        """A reading from before local midnight is yesterday's; it must
        not contribute to today's cumulative energy."""
        tz = datetime.now().astimezone().tzinfo
        today_local_midnight_utc_naive = (
            datetime.now(tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=today_local_midnight_utc_naive - timedelta(minutes=5),
                station_type=16,
                solar_radiation=800,
            ))
            db.commit()
        finally:
            db.close()
        _seed_today([(60, 500), (120, 500)])

        db = SessionLocal()
        try:
            energy = compute_daily_solar_energy_j_per_m2(db)
            # 500 W/m² * 3600s = 1_800_000 J/m². Yesterday's 800 W/m² sample
            # is upstream of the cutoff and must not be joined.
            assert energy == pytest.approx(500 * 3600, abs=1)
        finally:
            db.close()

    def test_zero_dt_intervals_skipped(self):
        """Two samples with identical timestamps (a poll landed twice on
        the same clock second) contribute nothing and don't crash."""
        tz = datetime.now().astimezone().tzinfo
        today_local_midnight_utc_naive = (
            datetime.now(tz)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        db = SessionLocal()
        try:
            same_ts = today_local_midnight_utc_naive + timedelta(minutes=600)
            db.add(SensorReadingModel(
                timestamp=same_ts, station_type=16, solar_radiation=500,
            ))
            db.add(SensorReadingModel(
                timestamp=same_ts, station_type=16, solar_radiation=500,
            ))
            db.add(SensorReadingModel(
                timestamp=same_ts + timedelta(minutes=60),
                station_type=16, solar_radiation=500,
            ))
            db.commit()
            energy = compute_daily_solar_energy_j_per_m2(db)
            # First pair is zero-dt; second pair is 500 * 3600.
            assert energy == pytest.approx(500 * 3600, abs=1)
        finally:
            db.close()


class TestDisplayUnitConversion:
    """J/m² → the operator's chosen unit."""

    def test_mj_per_m2(self):
        # 1.8 MJ/m² per hour of 500 W/m² (see trapezoid tests above).
        assert joules_to_display_unit(1_800_000, "MJ/m²") == pytest.approx(1.80)

    def test_kwh_per_m2(self):
        # 1.8 MJ = 0.5 kWh (3.6 MJ = 1 kWh).
        assert joules_to_display_unit(1_800_000, "kWh/m²") == pytest.approx(0.5)

    def test_wh_per_m2(self):
        # 1.8 MJ = 500 Wh.
        assert joules_to_display_unit(1_800_000, "Wh/m²") == pytest.approx(500.0)

    def test_none_input_none_output(self):
        assert joules_to_display_unit(None, "MJ/m²") is None

    def test_unknown_unit_returns_none(self):
        # API layer is expected to validate but we don't crash.
        assert joules_to_display_unit(1_000_000, "gigafoot") is None

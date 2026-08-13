"""Daily solar-energy history — one value per local calendar day.

Extends ``solar_energy.py`` with ``compute_daily_solar_energy_series``
and adds ``GET /api/history/solar-energy`` as the second half of the
"historical charting for solar/ET" work.

The single-day integrator (``compute_daily_solar_energy_j_per_m2``)
already has its own test file; this one covers the multi-day bucketing
and API-shape guarantees.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.models.station_config import StationConfigModel
from app.services.solar_energy import compute_daily_solar_energy_series


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


def _seed_row(offset_from_local_midnight_min: int, day_offset: int, flux: int) -> None:
    """Seed a sensor reading at (today - day_offset) days ago, at N minutes
    after the local midnight of that day.  day_offset=0 is today,
    day_offset=1 is yesterday, etc.  All in the system-local tz."""
    tz = datetime.now().astimezone().tzinfo
    today_local_midnight = datetime.now(tz).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    target_local_midnight = today_local_midnight - timedelta(days=day_offset)
    ts_local = target_local_midnight + timedelta(minutes=offset_from_local_midnight_min)
    ts_utc_naive = ts_local.astimezone(timezone.utc).replace(tzinfo=None)
    db = SessionLocal()
    try:
        db.add(SensorReadingModel(
            timestamp=ts_utc_naive,
            station_type=16,
            solar_radiation=flux,
        ))
        db.commit()
    finally:
        db.close()


class TestMultiDayBucketing:
    def test_empty_returns_all_none(self):
        """Fresh DB → 3-day request returns 3 entries with value None."""
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=3)
        finally:
            db.close()
        assert len(series) == 3
        assert all(entry["j_per_m2"] is None for entry in series)

    def test_two_samples_one_day(self):
        """500 W/m² held for 1 hour → 500 * 3600 = 1.8 MJ/m² for that day.
        Other days in the window are None."""
        _seed_row(600, day_offset=1, flux=500)  # yesterday 10:00
        _seed_row(660, day_offset=1, flux=500)  # yesterday 11:00
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=3)
        finally:
            db.close()
        # Oldest first: 2 days ago, yesterday, today
        assert len(series) == 3
        assert series[0]["j_per_m2"] is None
        assert series[1]["j_per_m2"] == pytest.approx(500 * 3600, abs=1)
        assert series[2]["j_per_m2"] is None

    def test_bucketing_respects_local_midnight(self):
        """A sample 5 minutes before local midnight belongs to yesterday;
        a sample 5 minutes after belongs to today."""
        _seed_row(-5, day_offset=0, flux=400)   # yesterday 23:55 (5 min before today's midnight)
        _seed_row(5, day_offset=0, flux=400)    # today 00:05
        _seed_row(65, day_offset=0, flux=400)   # today 01:05 (1hr after prev)
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=2)
        finally:
            db.close()
        # Two entries: yesterday and today
        assert len(series) == 2
        # Yesterday: only one sample (the -5 min) fell there → None
        assert series[0]["j_per_m2"] is None
        # Today: 00:05 → 01:05 = 3600s at 400 W/m² = 1_440_000 J/m²
        assert series[1]["j_per_m2"] == pytest.approx(400 * 3600, abs=1)

    def test_days_clamped_below_one(self):
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=0)
        finally:
            db.close()
        assert len(series) == 1  # clamped to 1

    def test_days_clamped_above_366(self):
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=1000)
        finally:
            db.close()
        assert len(series) == 366  # clamped to 366

    def test_dates_are_sequential_and_iso(self):
        """Each entry has an ISO-format `date` and the sequence is
        consecutive days, oldest first."""
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=5)
        finally:
            db.close()
        assert len(series) == 5
        dates = [datetime.fromisoformat(e["date"]) for e in series]
        for prev, curr in zip(dates, dates[1:]):
            assert (curr - prev).days == 1

    def test_partial_today_still_returned(self):
        """Today can have any number of samples (including few) — it's a
        partial-day value that just includes whatever's arrived so far."""
        _seed_row(60, day_offset=0, flux=300)   # today 01:00
        _seed_row(120, day_offset=0, flux=300)  # today 02:00
        db = SessionLocal()
        try:
            series = compute_daily_solar_energy_series(db, days=1)
        finally:
            db.close()
        # 300 W/m² * 3600s = 1_080_000 J/m²
        assert series[-1]["j_per_m2"] == pytest.approx(300 * 3600, abs=1)


class TestApiEndpoint:
    def test_shape(self):
        client = TestClient(app)
        r = client.get("/api/history/solar-energy?days=3")
        assert r.status_code == 200
        body = r.json()
        assert "unit" in body
        assert body["days"] == 3
        assert isinstance(body["points"], list)
        assert len(body["points"]) == 3
        for pt in body["points"]:
            assert "date" in pt
            assert "value" in pt

    def test_default_days_is_14(self):
        client = TestClient(app)
        r = client.get("/api/history/solar-energy")
        assert r.status_code == 200
        assert r.json()["days"] == 14
        assert len(r.json()["points"]) == 14

    def test_unit_conversion_applied(self):
        """500 W/m² for 3600s = 1_800_000 J/m² = 1.80 MJ/m².  Verify the
        endpoint returns the MJ/m² value directly (not raw joules).
        """
        _seed_row(600, day_offset=0, flux=500)
        _seed_row(660, day_offset=0, flux=500)
        # Set the user's preferred unit to MJ/m² explicitly
        db = SessionLocal()
        try:
            db.add(StationConfigModel(
                key="solar_energy_unit",
                value="MJ/m²",
                updated_at=datetime.now(timezone.utc),
            ))
            db.commit()
        finally:
            db.close()

        client = TestClient(app)
        r = client.get("/api/history/solar-energy?days=1")
        assert r.status_code == 200
        body = r.json()
        assert body["unit"] == "MJ/m²"
        assert body["points"][-1]["value"] == pytest.approx(1.80, abs=0.01)

    def test_days_out_of_range_rejected(self):
        """FastAPI's Query(ge=1, le=366) enforces the bounds at the
        API layer, not just in the service — this catches an operator
        typing `days=0` or `days=999999`."""
        client = TestClient(app)
        assert client.get("/api/history/solar-energy?days=0").status_code == 422
        assert client.get("/api/history/solar-energy?days=367").status_code == 422

    def test_null_values_for_empty_days(self):
        """A window with no samples returns entries with value: null.
        The frontend can use these to render a gap."""
        client = TestClient(app)
        r = client.get("/api/history/solar-energy?days=3")
        assert r.status_code == 200
        assert all(pt["value"] is None for pt in r.json()["points"])

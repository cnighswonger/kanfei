"""Aggregate resolutions on ``GET /api/history`` must collapse rows.

Regression test for the "5m returns 8k raw points instead of ~288"
class of bug: SQLAlchemy 2.0's Python-level ``/`` operator on numeric
columns emits ``x / (300 + 0.0)`` for SQLite, and float division puts
every unix-timestamp second into its own bucket — the ``GROUP BY``
silently doesn't collapse.  We force integer division at the SQL layer
with ``.op("/")``; this test would fail if that ever regressed.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel


client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_tables():
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


def _seed_raw(hours: float, per_minute: int, base_temp_tenths_c: int = 220) -> None:
    """Seed ``per_minute`` samples per minute over the last ``hours`` hours."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    db = SessionLocal()
    try:
        rows = []
        total_min = int(hours * 60)
        for m in range(total_min):
            for k in range(per_minute):
                ts = start + timedelta(minutes=m, seconds=(60 // per_minute) * k)
                rows.append(SensorReadingModel(
                    timestamp=ts,
                    station_type=17,  # Vantage Vue
                    outside_temp=base_temp_tenths_c,
                ))
        db.add_all(rows)
        db.commit()
    finally:
        db.close()


def _range(hours: float) -> tuple[str, str]:
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    start = end - timedelta(hours=hours)
    return start.isoformat(), end.isoformat()


def test_5m_collapses_to_five_minute_buckets():
    """6 samples/min over 24 h = 8640 raw; 5-min buckets = ~288."""
    _seed_raw(hours=24, per_minute=6)
    start, end = _range(24)
    r = client.get(f"/api/history?sensor=outside_temp&start={start}&end={end}&resolution=5m")
    assert r.status_code == 200
    body = r.json()
    assert body["resolution"] == "5m"
    n = len(body["points"])
    # 24 h * 12 buckets/hour = 288.  Allow one extra bucket on either
    # end where the window doesn't align to a bucket boundary.
    assert 285 <= n <= 290, f"expected ~288 5-min points, got {n}"


def test_hourly_collapses_to_hourly_buckets():
    _seed_raw(hours=24, per_minute=6)
    start, end = _range(24)
    r = client.get(f"/api/history?sensor=outside_temp&start={start}&end={end}&resolution=hourly")
    assert r.status_code == 200
    body = r.json()
    n = len(body["points"])
    assert 23 <= n <= 25, f"expected ~24 hourly points, got {n}"


def test_raw_returns_every_sample():
    _seed_raw(hours=1, per_minute=6)
    start, end = _range(1)
    r = client.get(f"/api/history?sensor=outside_temp&start={start}&end={end}&resolution=raw")
    assert r.status_code == 200
    body = r.json()
    # 60 min * 6 per min = 360 raw points.  Boundary rows can drop
    # from spike detection (LAG/LEAD null at the edges); allow one.
    assert 359 <= len(body["points"]) <= 360


def test_5m_labels_land_on_bucket_starts():
    """Regression: two sensors sampled at different phases within the
    same 5-minute bucket must return *identical* timestamps for that
    bucket.  Before this fix, ``time_label`` was ``strftime(...ts_col)``
    on a raw row SQLite picked from each group — so temperature's
    12:40-bucket labelled as ``12:44:00`` and dew's same bucket
    labelled as ``12:45:00``.  Highcharts then drew the two series
    at slightly different x positions (visible as a tooltip drift
    across series when the user dragged the cursor).
    """
    _seed_raw(hours=1, per_minute=6)
    start, end = _range(1)
    r = client.get(f"/api/history?sensor=outside_temp&start={start}&end={end}&resolution=5m")
    body = r.json()
    # Every returned label must be a bucket START — minute ends in
    # 0 or 5 (5-minute grid) and seconds are ``:00``.
    for pt in body["points"]:
        ts = pt["timestamp"]
        assert ts.endswith(":00Z"), f"seconds not :00 for {ts}"
        minute = int(ts[14:16])
        assert minute % 5 == 0, f"minute {minute} not a 5-minute-grid multiple ({ts})"

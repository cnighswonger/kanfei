"""``_get_latest_obs`` must not surface the day's max wind as a "gust".

Regression pin for the 2026-08-24 Design v52 §1 finding:  the wind
constraint on the Agriculture verdict tile was blocking a spray with
``Wind 9 mph ≤ 8 mph ✗`` while the live wind was 0 mph and the day's
peak wind was from 14:41 — seven hours earlier.  The peak-since-
midnight was being loaded into ``wind_gust_mph`` inside
``_get_latest_obs`` and then piped through ``_check_wind``, which
prefers gust over sustained.  Result: an unqualified ``Wind`` row
that silently means "day's peak," and a NO-GO verdict on a gust the
rest of the page (Drift risk = 0 mph, Peak 9 mph 14:41 as separate
context) disproved.

The fix drops the ``wind_gust_mph`` key from the current-obs shape.
Consumers that need a legitimate current-window gust (currently just
``get_spray_conditions``) still fall back to Open-Meteo's
``wind_gusts_10m[0]`` — a real current-hour forecast gust.  The
day's peak context stays available on the Drift-risk tile via
``daily_extremes.wind_speed_hi`` in ``/api/current``.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.api.spray import _get_latest_obs
from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel


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


def _seed_readings(sustained_mph_now: float, peak_mph_earlier: float) -> None:
    """Two rows: an earlier peak (14:41-ish) plus a current calm reading.

    Values are stored as tenths of m/s (native ``wind_speed`` column
    scale) — the same convention ``Poller`` uses for live rows.
    """
    def mph_to_tenths_ms(mph: float) -> int:
        # 1 mph = 0.44704 m/s; tenths → int
        return round(mph * 0.44704 * 10)

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        earlier = now.replace(hour=14, minute=41, second=0, microsecond=0)
        db.add(SensorReadingModel(
            timestamp=earlier.replace(tzinfo=None),
            station_type=17,
            wind_speed=mph_to_tenths_ms(peak_mph_earlier),
        ))
        db.add(SensorReadingModel(
            timestamp=now.replace(tzinfo=None),
            station_type=17,
            wind_speed=mph_to_tenths_ms(sustained_mph_now),
        ))
        db.commit()
    finally:
        db.close()


def test_wind_gust_mph_is_absent_when_only_stored_signal_is_day_peak():
    """The Design v52 shape: no ``wind_gust_mph`` in the current-obs
    dict when the only "gust" candidate we have is the day's max.
    A downstream ``_check_wind`` then falls through to sustained,
    which is what the "station now" kicker actually promises."""
    _seed_readings(sustained_mph_now=0.0, peak_mph_earlier=9.0)
    db = SessionLocal()
    try:
        obs = _get_latest_obs(db)
    finally:
        db.close()
    assert "wind_gust_mph" not in obs, (
        "Day's-max wind was being surfaced as gust; the constraint row "
        "then failed on a peak from hours earlier (Design v52 §1)."
    )
    # Sustained wind still lands, and it's the calm current sample —
    # not the earlier peak.
    assert obs.get("wind_speed_mph") is not None
    assert obs["wind_speed_mph"] < 1.0


def test_missing_wind_gust_lets_check_wind_use_sustained():
    """The load-bearing end-to-end: the constraint eval reads
    ``obs.get("wind_gust_mph")``, which is now None, so ``_check_wind``
    labels the row as sustained.  Reproduces Design v52 §1's fixture
    values."""
    from app.services.spray_engine import _check_wind
    _seed_readings(sustained_mph_now=0.0, peak_mph_earlier=9.0)
    db = SessionLocal()
    try:
        obs = _get_latest_obs(db)
    finally:
        db.close()
    check = _check_wind(
        obs.get("wind_speed_mph"),
        obs.get("wind_gust_mph"),
        max_wind=8.0,
    )
    assert check.passed, (
        "Sustained 0 mph must pass an 8 mph limit — the failure Design "
        "v52 §1 flagged was the day's peak (9 mph) sneaking through as "
        "gust and blocking the verdict."
    )
    assert "sustained" in check.current_value

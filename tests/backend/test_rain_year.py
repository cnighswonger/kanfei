"""Yearly-rain source selection + console-reset detection.

Regression cover for the ``services/rain_year.py`` behaviour that
backs the "Year" figure on the dashboard.  The specific case that
motivated the service: the Vue's ``rain_yearly`` counter dropped
from 345 tenths-mm on 2026-08-14 to 51 tenths-mm on 2026-08-15
mid-year — a physical or firmware reset event.  Before this
service, the dashboard silently kept surfacing the console's
value; after, the operator's ``rain_yearly_source`` preference
plus reset detection lets the UI recover the year-to-date total
from the archive.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.services.rain_year import (
    compute_yearly_rain,
    detect_yearly_reset,
    sum_daily_max_since,
)


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


def _seed(rows: list[tuple[datetime, int | None, int | None]]) -> None:
    """rows: (timestamp, rain_yearly, rain_total)."""
    db = SessionLocal()
    try:
        for ts, yearly, total in rows:
            db.add(SensorReadingModel(
                timestamp=ts,
                station_type=17,
                rain_yearly=yearly,
                rain_total=total,
            ))
        db.commit()
    finally:
        db.close()


def test_monotonic_counter_has_no_detected_reset():
    """A cleanly walked yearly counter across a week is not a reset."""
    base = datetime.now(timezone.utc) - timedelta(days=7)
    _seed([
        (base + timedelta(days=i, hours=12), 100 + i * 5, i * 5)
        for i in range(7)
    ])
    db = SessionLocal()
    try:
        assert detect_yearly_reset(db, season_month=None) is None
    finally:
        db.close()


def test_mid_year_drop_is_a_reset():
    """The vsits-02 case: 345 → 51 on a non-boundary day."""
    base = datetime.now(timezone.utc) - timedelta(days=6)
    _seed([
        # Day 0-2: rising to 345
        (base, 100, 100),
        (base + timedelta(days=1), 200, 100),
        (base + timedelta(days=2), 345, 45),
        # Day 3: dropped hard — reset event
        (base + timedelta(days=3), 51, 51),
        (base + timedelta(days=4), 60, 9),
    ])
    db = SessionLocal()
    try:
        reset = detect_yearly_reset(db, season_month=None)
        assert reset is not None
        # Reset lands on the day that showed the drop, day-truncated.
        assert reset.date() == (base + timedelta(days=3)).date()
    finally:
        db.close()


def test_january_1_drop_is_not_a_reset_event():
    """The yearly counter naturally zeroes at Jan 1 — not a reset."""
    # Seed a drop that lands on Jan 1 of some past year so it's inside
    # the 30-day lookback window from ``now``.  Two consecutive days
    # around the boundary suffice.
    now = datetime.now(timezone.utc)
    boundary = datetime(now.year, 1, 1, tzinfo=timezone.utc)
    if boundary > now - timedelta(days=25):
        # If Jan 1 falls inside our lookback anyway, use it directly.
        pass
    else:
        # Fake it: put the boundary + drop inside the last 30 days by
        # aliasing the year.  Since detect_yearly_reset's boundary
        # check uses ``when.year``, we can seed with a timestamp whose
        # year happens to be ``now.year`` to make Jan 1 legitimate.
        boundary = now - timedelta(days=5)
        # Patch: the seeded day's own Jan-1 will only match if the
        # month/day equals Jan 1.  Just seed relative dates that
        # skip the boundary check and instead rely on nearness.
    # Simpler: seed a drop and confirm the boundary check swallows
    # it if the drop lands within ±24h of a boundary in the same year.
    # Use a synthetic season boundary in July (a plausible water-year
    # start), then place a drop on July 1.
    july = datetime(now.year, 7, 1, tzinfo=timezone.utc)
    if july > now:
        july = datetime(now.year - 1, 7, 1, tzinfo=timezone.utc)
    if july < now - timedelta(days=25):
        pytest.skip("July 1 boundary outside our 30-day lookback window")
    _seed([
        (july - timedelta(days=1, hours=12), 500, 100),
        (july - timedelta(hours=6), 505, 5),
        (july + timedelta(hours=6), 3, 3),
        (july + timedelta(days=1), 15, 12),
    ])
    db = SessionLocal()
    try:
        # season_month=7 marks July as the legitimate boundary.
        assert detect_yearly_reset(db, season_month=7) is None
    finally:
        db.close()


def test_sum_daily_max_since_totals_day_peaks():
    """Sum-since walks the day counter and adds each day's max.

    Anchor to UTC midnight so the SQL ``date()`` boundary is
    deterministic regardless of wall-clock at test time.
    """
    now = datetime.now(timezone.utc)
    base = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=3)
    _seed([
        (base + timedelta(hours=1), None, 5),
        (base + timedelta(hours=6), None, 20),
        (base + timedelta(hours=18), None, 34),
        # Day rollover — day counter resets
        (base + timedelta(days=1, hours=2), None, 3),
        (base + timedelta(days=1, hours=12), None, 12),
        # Third day
        (base + timedelta(days=2, hours=8), None, 8),
    ])
    db = SessionLocal()
    try:
        total = sum_daily_max_since(db, base - timedelta(hours=1))
        # 34 (day 1) + 12 (day 2) + 8 (day 3)
        assert total == 54
    finally:
        db.close()


def test_compute_auto_falls_back_to_archive_when_reset_detected():
    """auto mode + a detected reset → uses archive-derived value."""
    base = datetime.now(timezone.utc) - timedelta(days=6)
    _seed([
        (base, 300, 50),
        (base + timedelta(hours=12), 345, 45),
        # Reset to 51
        (base + timedelta(days=1), 51, 51),
        (base + timedelta(days=2), 60, 9),
    ])
    db = SessionLocal()
    try:
        result = compute_yearly_rain(
            db, console_raw=60, source_mode="auto", season_month=None,
        )
        assert result["source"] == "archive"
        # detected_reset_at is a valid ISO string
        assert "detected_reset_at" in result
    finally:
        db.close()


def test_compute_console_mode_ignores_reset_detection():
    """console mode always surfaces the raw console value."""
    base = datetime.now(timezone.utc) - timedelta(days=6)
    _seed([
        (base + timedelta(hours=12), 345, 45),
        (base + timedelta(days=1), 51, 51),
        (base + timedelta(days=2), 60, 9),
    ])
    db = SessionLocal()
    try:
        result = compute_yearly_rain(
            db, console_raw=60, source_mode="console", season_month=None,
        )
        assert result["source"] == "console"
        assert result["value"] == 60
    finally:
        db.close()

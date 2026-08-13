"""Console sunrise/sunset override on the astronomy API (#237).

Davis Vantage LOOP2 supplies the console's own sunrise/sunset — the
values it computes from its configured lat/lon and shows on the LCD.
When present in the latest ``sensor_readings.extra_json``, the API
returns those in place of astral's computation so the dashboard and
the console face agree.

Encoding: Davis packs sunrise/sunset as a single integer, ``hour*100
+ minute`` (e.g. 615 → 06:15, 1930 → 19:30) in the console's local
time.  Absence, out-of-range values, and the wire-audit ``0``
sentinel all fall back to astral.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.api.astronomy import (
    _fmt_hhmm_console,
    _read_console_sun_times,
)
from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel


@pytest.fixture(autouse=True)
def _clean_sensor_readings():
    Base.metadata.drop_all(bind=engine, tables=[SensorReadingModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[SensorReadingModel.__table__])
    yield
    db = SessionLocal()
    try:
        db.query(SensorReadingModel).delete()
        db.commit()
    finally:
        db.close()


def _seed(extras: dict | None, ago_seconds: int = 0) -> None:
    db = SessionLocal()
    try:
        db.add(SensorReadingModel(
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(seconds=ago_seconds),
            station_type=16,
            extra_json=json.dumps(extras) if extras is not None else None,
        ))
        db.commit()
    finally:
        db.close()


class TestHhmmFormat:
    def test_morning(self):
        assert _fmt_hhmm_console(615) == "6:15 AM"

    def test_evening(self):
        assert _fmt_hhmm_console(1930) == "7:30 PM"

    def test_noon_boundary(self):
        # 12:00 is 12:00 PM (noon), not 0:00 PM
        assert _fmt_hhmm_console(1200) == "12:00 PM"

    def test_midnight_boundary(self):
        # 00:00 is 12:00 AM in the 12-hour convention — but see the
        # `test_zero_returns_none` case: this method treats 0 as the
        # wire-audit sentinel and returns None instead.
        # 30 minutes past midnight is a valid 12:30 AM.
        assert _fmt_hhmm_console(30) == "12:30 AM"

    def test_padding_on_single_digit_minute(self):
        # 615 = 6:15, but 605 must render 6:05 (not 6:5)
        assert _fmt_hhmm_console(605) == "6:05 AM"

    def test_none_returns_none(self):
        assert _fmt_hhmm_console(None) is None

    def test_zero_returns_none(self):
        """The wire audit saw sunrise = 0 when LOOP2 offsets were wrong
        (§M2). Treat exactly 0 as an unreliable/absent value — astral
        will do a better job than showing "12:00 AM"."""
        assert _fmt_hhmm_console(0) is None

    def test_out_of_range_hour_returns_none(self):
        # hour = 24 would come from an integer 2400 — nonsensical
        assert _fmt_hhmm_console(2400) is None

    def test_out_of_range_minute_returns_none(self):
        # minute = 60 from 660: bounds guard catches it
        assert _fmt_hhmm_console(660) is None

    def test_bogus_large_value_returns_none(self):
        # The old parser bug produced sunset = 10497 (§M2)
        assert _fmt_hhmm_console(10497) is None


class TestConsoleReadNoData:
    def test_empty_db(self):
        assert _read_console_sun_times() == (None, None)

    def test_null_extras(self):
        _seed(None)
        assert _read_console_sun_times() == (None, None)

    def test_extras_without_sun_keys(self):
        _seed({"bar_trend": 60})
        assert _read_console_sun_times() == (None, None)

    def test_bad_json(self):
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json="{bad json",
            ))
            db.commit()
        finally:
            db.close()
        assert _read_console_sun_times() == (None, None)

    def test_non_dict_root(self):
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json="[1,2,3]",
            ))
            db.commit()
        finally:
            db.close()
        assert _read_console_sun_times() == (None, None)


class TestConsoleReadHappyPath:
    def test_both_present(self):
        _seed({"sunrise": 615, "sunset": 1930})
        assert _read_console_sun_times() == ("6:15 AM", "7:30 PM")

    def test_only_sunrise_present(self):
        _seed({"sunrise": 615})
        assert _read_console_sun_times() == ("6:15 AM", None)

    def test_only_sunset_present(self):
        _seed({"sunset": 1930})
        assert _read_console_sun_times() == (None, "7:30 PM")

    def test_sunrise_zero_falls_back(self):
        """Sentinel-zero sunrise → None (caller uses astral); sunset
        still returns its own value if it's real."""
        _seed({"sunrise": 0, "sunset": 1930})
        assert _read_console_sun_times() == (None, "7:30 PM")

    def test_latest_row_wins(self):
        _seed({"sunrise": 500, "sunset": 1830}, ago_seconds=3600)
        _seed({"sunrise": 615, "sunset": 1930}, ago_seconds=0)
        assert _read_console_sun_times() == ("6:15 AM", "7:30 PM")

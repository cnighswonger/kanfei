"""Battery-status parsing from ``sensor_readings.extra_json`` on the
``/api/station`` handler.

Battery data lives in ``extra_json`` alongside the other LOOP2/vendor
fields (see #236). This test file pins the shape ``/api/station``
returns so the operator sees a low battery before it turns into a
sentinel outage (the class of failure #230 documents).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.api.station import _read_battery_from_latest_reading
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


def _seed_row(extra: dict | None, ago_seconds: int = 0) -> None:
    db = SessionLocal()
    try:
        db.add(SensorReadingModel(
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=ago_seconds),
            station_type=16,
            extra_json=json.dumps(extra) if extra is not None else None,
        ))
        db.commit()
    finally:
        db.close()


class TestNoData:
    def test_empty_db_returns_none(self):
        assert _read_battery_from_latest_reading() is None

    def test_row_with_null_extras_returns_none(self):
        _seed_row(None)
        assert _read_battery_from_latest_reading() is None

    def test_row_with_no_battery_keys_returns_none(self):
        """Row has extra_json but nothing battery-related — non-Davis
        drivers today, or a Davis driver where LOOP1 battery didn't
        parse.  We hide the row entirely rather than showing a blank."""
        _seed_row({"bar_trend": 60, "forecast_rule": 3})
        assert _read_battery_from_latest_reading() is None


class TestDataPresent:
    def test_full_battery_data(self):
        """Vantage LOOP1 populates all three keys.  All three make it
        through the parser."""
        _seed_row({
            "transmitter_battery_status": 0x05,          # bits 0 and 2 set
            "transmitters_low_battery": [1, 3],          # 1-indexed IDs
            "console_battery_voltage": 4.72,
        })
        result = _read_battery_from_latest_reading()
        assert result == {
            "transmitters_low": [1, 3],
            "console_voltage": 4.72,
            "raw_transmitter_bitmask": 0x05,
        }

    def test_all_transmitters_ok(self):
        """No low-battery IDs is a real 'all OK' state — the empty list
        must be preserved so the frontend can distinguish 'OK' (empty
        list) from 'unknown' (whole row null)."""
        _seed_row({
            "transmitter_battery_status": 0,
            "transmitters_low_battery": [],
            "console_battery_voltage": 4.75,
        })
        result = _read_battery_from_latest_reading()
        assert result["transmitters_low"] == []
        assert result["console_voltage"] == 4.75
        assert result["raw_transmitter_bitmask"] == 0

    def test_console_voltage_only(self):
        """A driver that reports console voltage but not the TX status —
        we still surface what we have."""
        _seed_row({"console_battery_voltage": 3.14})
        result = _read_battery_from_latest_reading()
        assert result == {
            "transmitters_low": [],
            "console_voltage": 3.14,
            "raw_transmitter_bitmask": None,
        }

    def test_tx_status_only(self):
        """And the reverse — a driver that reports the transmitter
        bitmask/decode but no console voltage."""
        _seed_row({
            "transmitter_battery_status": 0x02,
            "transmitters_low_battery": [2],
        })
        result = _read_battery_from_latest_reading()
        assert result == {
            "transmitters_low": [2],
            "console_voltage": None,
            "raw_transmitter_bitmask": 0x02,
        }


class TestLatestRowUsed:
    def test_latest_wins_over_older(self):
        _seed_row({"console_battery_voltage": 4.0}, ago_seconds=3600)
        _seed_row({"console_battery_voltage": 4.7}, ago_seconds=0)
        result = _read_battery_from_latest_reading()
        assert result["console_voltage"] == 4.7


class TestMalformedInputs:
    def test_bad_json_returns_none(self):
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json="{{not json",
            ))
            db.commit()
        finally:
            db.close()
        assert _read_battery_from_latest_reading() is None

    def test_non_dict_extras_returns_none(self):
        """extra_json is expected to be an object; if a bug elsewhere
        wrote an array or scalar, don't crash."""
        db = SessionLocal()
        try:
            db.add(SensorReadingModel(
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                station_type=16,
                extra_json='[1, 2, 3]',
            ))
            db.commit()
        finally:
            db.close()
        assert _read_battery_from_latest_reading() is None

    def test_wrong_type_tx_low_falls_back_to_empty(self):
        """Defensive: if `transmitters_low_battery` is somehow not a
        list, don't propagate garbage — treat as empty."""
        _seed_row({
            "transmitters_low_battery": "not a list",
            "console_battery_voltage": 4.5,
        })
        result = _read_battery_from_latest_reading()
        # console_voltage was still present, so the whole result isn't None
        assert result["console_voltage"] == 4.5
        assert result["transmitters_low"] == []

"""Tests for the archive_records -> sensor_readings projection bridge.

The bridge backfills the history chart (which reads only sensor_readings)
with rows derived from Davis archive records pulled out of the link's SRAM
during async_sync_archive.
"""

from datetime import datetime

import pytest

from app.models.archive_record import ArchiveRecordModel
from app.models.database import Base, SessionLocal, engine
from app.models.sensor_reading import SensorReadingModel
from app.services.archive_sync import (
    _project_to_sensor_reading,
    _valid_archive_baro,
    _valid_archive_humidity,
    _valid_archive_solar,
    _valid_archive_temp,
    _valid_archive_u8,
)
from app.utils.units import f_tenths_to_c_tenths, inhg_thousandths_to_hpa_tenths, mph_to_ms_tenths


@pytest.fixture(autouse=True)
def _setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    db = SessionLocal()
    db.query(SensorReadingModel).delete()
    db.query(ArchiveRecordModel).delete()
    db.commit()
    db.close()


def _basic_record(record_time=None, **overrides):
    """Build a parsed-archive dict matching backend/app/services/archive_sync.py
    _parse_basic_archive output (Davis native units: 1/10 °F, 1/1000 inHg, mph,
    %, 0–15 compass code)."""
    rec = {
        "archive_address": 0x0000,
        "record_time": record_time or datetime(2026, 5, 15, 12, 0, 0),
        "station_type": 16,
        "barometer": 29920,            # 29.920 inHg
        "inside_humidity": 45,
        "outside_humidity": 60,
        "rain_in_period": 0,
        "inside_temp_avg": 720,        # 72.0 °F
        "outside_temp_avg": 680,       # 68.0 °F
        "wind_speed_avg": 10,          # 10 mph
        "wind_direction": 4,           # E (90°)
        "outside_temp_hi": 695,
        "wind_gust": 18,               # 18 mph
        "outside_temp_lo": 665,
    }
    rec.update(overrides)
    return rec


class TestProjection:

    def test_units_converted_to_si_tenths(self):
        rec = _basic_record()
        out = _project_to_sensor_reading(rec)

        assert out.outside_temp == f_tenths_to_c_tenths(680)
        assert out.inside_temp == f_tenths_to_c_tenths(720)
        assert out.barometer == inhg_thousandths_to_hpa_tenths(29920)
        assert out.wind_speed == mph_to_ms_tenths(10)
        assert out.wind_gust == mph_to_ms_tenths(18)
        assert out.outside_humidity == 60
        assert out.inside_humidity == 45

    def test_timestamp_passthrough(self):
        ts = datetime(2026, 5, 15, 11, 17, 0)
        out = _project_to_sensor_reading(_basic_record(record_time=ts))
        assert out.timestamp == ts

    def test_wind_direction_code_to_degrees(self):
        # Davis compass code 4 == E == 90°, code 8 == S == 180°
        assert _project_to_sensor_reading(
            _basic_record(wind_direction=4)).wind_direction == 90
        assert _project_to_sensor_reading(
            _basic_record(wind_direction=8)).wind_direction == 180
        # 0xFF (invalid) parses to None upstream — also handle 0
        assert _project_to_sensor_reading(
            _basic_record(wind_direction=0)).wind_direction == 0

    def test_wind_direction_none_when_missing(self):
        out = _project_to_sensor_reading(_basic_record(wind_direction=None))
        assert out.wind_direction is None

    def test_derived_fields_computed(self):
        # Warm-and-humid record should produce a dew point and feels-like.
        rec = _basic_record(outside_temp_avg=850, outside_humidity=70)  # 85°F/70%
        out = _project_to_sensor_reading(rec)
        assert out.dew_point is not None
        assert out.heat_index is not None
        assert out.feels_like is not None
        # theta_e needs baro; baro is provided in _basic_record
        assert out.theta_e is not None

    def test_wind_chill_only_when_cold_and_windy(self):
        cold_windy = _basic_record(outside_temp_avg=200, wind_speed_avg=20)  # 20°F/20mph
        out = _project_to_sensor_reading(cold_windy)
        assert out.wind_chill is not None

    def test_derived_skipped_when_inputs_missing(self):
        rec = _basic_record(outside_temp_avg=None, outside_humidity=None)
        out = _project_to_sensor_reading(rec)
        assert out.heat_index is None
        assert out.dew_point is None
        assert out.feels_like is None
        assert out.wind_chill is None
        assert out.theta_e is None

    def test_rain_left_null(self):
        # Per docstring: backfilled rows don't fill rain_total / rain_rate
        # because the schema is daily-cumulative / requires resolution decode.
        out = _project_to_sensor_reading(_basic_record())
        assert out.rain_total is None
        assert out.rain_rate is None


class TestSentinelFiltering:
    """Davis archive image uses sentinel values for invalid readings
    (database.txt:148-153).  The bridge must strip them before unit
    conversion so backfilled sensor_readings rows don't carry garbage
    like -1838 °C into user-facing surfaces."""

    def test_temp_minus_32768_is_invalid(self):
        # 0x8000 interpreted signed; Davis 'not connected' sentinel.
        assert _valid_archive_temp(-32768) is None

    def test_temp_32767_is_invalid(self):
        # 0x7FFF Davis sentinel.
        assert _valid_archive_temp(32767) is None

    def test_temp_out_of_range_is_invalid(self):
        assert _valid_archive_temp(3000) is None   # > 250 °F
        assert _valid_archive_temp(-1000) is None  # < -90 °F

    def test_temp_valid_passthrough(self):
        assert _valid_archive_temp(720) == 720  # 72.0 °F
        assert _valid_archive_temp(0) == 0      # 0.0 °F is a real value

    def test_baro_zero_is_invalid(self):
        assert _valid_archive_baro(0) is None

    def test_baro_ffff_is_invalid(self):
        assert _valid_archive_baro(0xFFFF) is None

    def test_baro_valid_passthrough(self):
        assert _valid_archive_baro(29920) == 29920

    def test_u8_ff_is_invalid(self):
        # Used for wind speed, gust, UV.
        assert _valid_archive_u8(0xFF) is None

    def test_u8_zero_is_valid(self):
        # 0 mph wind is a real reading, not invalid.
        assert _valid_archive_u8(0) == 0

    def test_humidity_128_is_invalid(self):
        # database.txt:151 — humidity invalid sentinel is 128 (0x80).
        assert _valid_archive_humidity(0x80) is None
        assert _valid_archive_humidity(0xFF) is None

    def test_humidity_valid_passthrough(self):
        assert _valid_archive_humidity(60) == 60
        assert _valid_archive_humidity(0) == 0

    def test_solar_invalid(self):
        assert _valid_archive_solar(0xFFF) is None
        assert _valid_archive_solar(0xFFFF) is None

    def test_solar_valid_passthrough(self):
        assert _valid_archive_solar(450) == 450

    def test_projection_strips_sentinels_end_to_end(self):
        rec = _basic_record(
            inside_temp_avg=-32768,
            outside_temp_avg=32767,
            barometer=0xFFFF,
            wind_speed_avg=0xFF,
            wind_gust=0xFF,
            inside_humidity=0x80,
            outside_humidity=0x80,
        )
        out = _project_to_sensor_reading(rec)
        assert out.inside_temp is None
        assert out.outside_temp is None
        assert out.barometer is None
        assert out.wind_speed is None
        assert out.wind_gust is None
        assert out.inside_humidity is None
        assert out.outside_humidity is None
        # Derived values must also be None when their inputs were sentinels.
        assert out.heat_index is None
        assert out.dew_point is None
        assert out.wind_chill is None
        assert out.feels_like is None
        assert out.theta_e is None

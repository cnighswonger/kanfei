"""Tests for the Weather Underground uploader, focused on per-channel mute.

The mute set is shared with CWOP via ``app.services.channel_mute``; this
module verifies that WU consults the same set and drops both the
directly-mapped WU field and any derived field that depends on the
muted sensor (issue #162).
"""

from unittest.mock import patch

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.services.channel_mute import MUTE_CHANNELS, mute_key
from app.services.wunderground import WundergroundUploader


@pytest.fixture
def wu_db():
    """Fresh station_config table seeded with the basic WU enable/creds."""
    Base.metadata.drop_all(bind=engine, tables=[StationConfigModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[StationConfigModel.__table__])
    db = SessionLocal()
    for key, value in [
        ("wu_enabled", "true"),
        ("wu_station_id", "KXXTEST1"),
        ("wu_station_key", "secret"),
        ("wu_upload_interval", "60"),
    ]:
        db.add(StationConfigModel(key=key, value=value))
    db.commit()
    db.close()
    yield
    db = SessionLocal()
    db.query(StationConfigModel).delete()
    db.commit()
    db.close()


def _set_mute(channel: str, value: bool) -> None:
    db = SessionLocal()
    try:
        db.add(StationConfigModel(key=mute_key(channel), value=str(value).lower()))
        db.commit()
    finally:
        db.close()


# Broadcast dict shaped like ``Poller._snapshot_to_dict`` output, with
# every field WU cares about populated so we can assert what's dropped.
_SAMPLE_BROADCAST = {
    "temperature": {
        "outside": {"value": 72.0},
        "inside": {"value": 68.0},
    },
    "humidity": {
        "outside": {"value": 50},
        "inside": {"value": 40},
    },
    "wind": {
        "speed": {"value": 10},
        "direction": {"value": 270},
    },
    "barometer": {"value": 29.92},
    "rain": {
        "daily": {"value": 0.12},
        "yearly": {"value": 4.5},
        "rate": {"value": 0.03},
    },
    "daily_extremes": {"wind_speed_hi": {"value": 15}},
    "derived": {
        "wind_chill": {"value": 70.0},
        "dew_point": {"value": 52.0},
        "heat_index": {"value": 75.0},
    },
    "solar_radiation": {"value": 250},
    "uv_index": {"value": 3},
}


# WU field → channel id that directly drops it.
_DIRECT_FIELD_BY_CHANNEL = {
    "outdoor_temperature": "tempf",
    "outdoor_humidity": "humidity",
    "wind_speed": "windspeedmph",
    "wind_direction": "winddir",
    "wind_gust": "windgustmph",
    "barometer": "baromin",
    "rain_daily": "dailyrainin",
    "rain_hour": "rainin",
}


class TestBuildParamsMute:
    """Each mute key drops its WU field (and any derived dependents)."""

    @pytest.mark.parametrize("channel", list(MUTE_CHANNELS))
    def test_muted_channel_drops_direct_field(self, wu_db, channel):
        _set_mute(channel, True)
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=0.05,
        ):
            up.reload_config()
            params = up._build_params(_SAMPLE_BROADCAST)

        if channel == "rain_24h":
            # No WU field corresponds to 24h rain — mute is a no-op.
            for f in _DIRECT_FIELD_BY_CHANNEL.values():
                assert f in params, f"{f!r} unexpectedly dropped by rain_24h mute"
        else:
            field = _DIRECT_FIELD_BY_CHANNEL[channel]
            assert field not in params, (
                f"channel {channel}: field {field!r} should be dropped"
            )

    def test_rain_daily_mute_drops_yearly_and_rate(self, wu_db):
        # The WU-only rain fields ``yearrainin`` and ``rainratein`` come from
        # the same physical gauge counter as ``dailyrainin``; muting the
        # primary rain channel must drop all three.
        _set_mute("rain_daily", True)
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=0.05,
        ):
            up.reload_config()
            params = up._build_params(_SAMPLE_BROADCAST)
        for f in ("dailyrainin", "yearrainin", "rainratein"):
            assert f not in params, f"{f!r} should be dropped when rain_daily muted"
        # Hourly rain comes from a separate query gate; still present.
        assert "rainin" in params

    def test_temperature_mute_drops_derived(self, wu_db):
        _set_mute("outdoor_temperature", True)
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=0.05,
        ):
            up.reload_config()
            params = up._build_params(_SAMPLE_BROADCAST)
        for f in ("tempf", "windchillf", "heatindexf", "dewptf"):
            assert f not in params, f"{f!r} should be dropped when temp muted"

    def test_humidity_mute_drops_derived(self, wu_db):
        _set_mute("outdoor_humidity", True)
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=0.05,
        ):
            up.reload_config()
            params = up._build_params(_SAMPLE_BROADCAST)
        for f in ("humidity", "heatindexf", "dewptf"):
            assert f not in params, f"{f!r} should be dropped when humidity muted"
        # tempf untouched — distinct sensor.
        assert "tempf" in params

    def test_wind_speed_mute_drops_windchill(self, wu_db):
        _set_mute("wind_speed", True)
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=0.05,
        ):
            up.reload_config()
            params = up._build_params(_SAMPLE_BROADCAST)
        assert "windspeedmph" not in params
        assert "windchillf" not in params
        # Heat index does not depend on wind — still present.
        assert "heatindexf" in params

    def test_no_mutes_emits_full_set(self, wu_db):
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=0.05,
        ):
            up.reload_config()
            params = up._build_params(_SAMPLE_BROADCAST)
        for f in (
            "tempf", "humidity", "windspeedmph", "windgustmph", "winddir",
            "baromin", "dailyrainin", "yearrainin", "rainratein", "rainin",
            "windchillf", "heatindexf", "dewptf", "solarradiation", "UV",
        ):
            assert f in params, f"{f!r} missing in unmuted output: {params!r}"

    def test_rain_query_skipped_when_rain_hour_muted(self, wu_db):
        _set_mute("rain_hour", True)
        up = WundergroundUploader()
        with patch.object(
            WundergroundUploader,
            "_get_hourly_rain_inches",
            return_value=0.05,
        ) as m:
            up.reload_config()
            up._build_params(_SAMPLE_BROADCAST)
            assert m.call_count == 0

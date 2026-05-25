"""Tests for CWOP upload service pure logic."""

from unittest.mock import patch

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.services.channel_mute import MUTE_CHANNELS, mute_key
from app.services.cwop import (
    CWOP_MUTE_CHANNELS,
    CwopUploader,
    _extract,
    _mute_key,
    aprs_passcode,
)


def test_compat_aliases_match_shared_module():
    # Compat re-exports in cwop.py must point at the canonical names.
    assert CWOP_MUTE_CHANNELS is MUTE_CHANNELS
    assert _mute_key is mute_key


class TestAprsPasscode:

    def test_cwop_callsign_returns_minus_one(self):
        assert aprs_passcode("CW1234") == "-1"
        assert aprs_passcode("DW5678") == "-1"
        assert aprs_passcode("EW9999") == "-1"

    def test_empty_callsign_returns_minus_one(self):
        assert aprs_passcode("") == "-1"
        assert aprs_passcode("  ") == "-1"

    def test_ham_callsign_exact_hash(self):
        assert aprs_passcode("N0CALL") == "13023"

    def test_case_insensitive(self):
        assert aprs_passcode("n0call") == "13023"

    def test_strips_ssid(self):
        # N0CALL-13 should hash same as N0CALL
        assert aprs_passcode("N0CALL-13") == "13023"

    def test_known_callsign_w3ado(self):
        assert aprs_passcode("W3ADO") == "10901"


class TestExtract:

    def test_simple_path(self):
        data = {"a": {"b": {"c": 42}}}
        assert _extract(data, ("a", "b", "c")) == 42

    def test_missing_key_returns_none(self):
        data = {"a": {"b": 1}}
        assert _extract(data, ("a", "x")) is None

    def test_single_key(self):
        data = {"temp": 72}
        assert _extract(data, ("temp",)) == 72

    def test_none_value_returns_none(self):
        data = {"a": None}
        assert _extract(data, ("a", "b")) is None

    def test_non_dict_intermediate_returns_none(self):
        data = {"a": 42}
        assert _extract(data, ("a", "b")) is None

    def test_empty_path(self):
        data = {"a": 1}
        assert _extract(data, ()) == data


# ---------------------------------------------------------------------------
# Per-channel CWOP mute (issue #161)
# ---------------------------------------------------------------------------


@pytest.fixture
def cwop_db():
    """Fresh station_config table seeded with the basic CWOP enable + location."""
    Base.metadata.drop_all(bind=engine, tables=[StationConfigModel.__table__])
    Base.metadata.create_all(bind=engine, tables=[StationConfigModel.__table__])
    db = SessionLocal()
    for key, value in [
        ("cwop_enabled", "true"),
        ("cwop_callsign", "CW1234"),
        ("cwop_upload_interval", "300"),
        ("latitude", "49.0583"),
        ("longitude", "-72.0292"),
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
        db.add(StationConfigModel(key=_mute_key(channel), value=str(value).lower()))
        db.commit()
    finally:
        db.close()


_SAMPLE_BROADCAST = {
    "temperature": {"outside": {"value": 72.0}},
    "humidity": {"outside": {"value": 50}},
    "wind": {
        "speed": {"value": 10},
        "direction": {"value": 270},
    },
    "barometer": {"value": 29.92},
    "rain": {"daily": {"value": 0.12}},
    "daily_extremes": {"wind_speed_hi": {"value": 15}},
}


_SENTINEL_BY_CHANNEL = {
    "outdoor_temperature": "t...",
    "outdoor_humidity": "h..",
    "wind_speed": "_270/...",
    "wind_direction": "_.../010",
    "wind_gust": "g...",
    "barometer": "b.....",
    "rain_daily": "P...",
    "rain_hour": "r...",
    "rain_24h": "p...",
}


class TestBuildPacketMute:
    """Each mute key swaps the corresponding APRS field for its sentinel."""

    @pytest.mark.parametrize("channel", list(CWOP_MUTE_CHANNELS))
    def test_muted_channel_emits_sentinel(self, cwop_db, channel):
        _set_mute(channel, True)

        uploader = CwopUploader()
        # Bypass DB rain-accumulation query so the test doesn't depend on
        # sensor_readings; returns 0 tenths mm = 0 hundredths inch.
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            packet = uploader._build_packet(_SAMPLE_BROADCAST)

        assert packet is not None
        assert _SENTINEL_BY_CHANNEL[channel] in packet, (
            f"channel {channel}: sentinel {_SENTINEL_BY_CHANNEL[channel]!r} "
            f"not found in {packet!r}"
        )

    def test_temperature_missing_without_mute_returns_none(self, cwop_db):
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            data = {**_SAMPLE_BROADCAST, "temperature": {"outside": {"value": None}}}
            assert uploader._build_packet(data) is None

    def test_temperature_missing_with_mute_still_builds_packet(self, cwop_db):
        """Operator explicitly muted the channel — emit `t...` even if the
        underlying reading is also missing.  This is the whole point of the
        feature: keep the rest of the station live while a sensor is offline.
        """
        _set_mute("outdoor_temperature", True)
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            data = {**_SAMPLE_BROADCAST, "temperature": {"outside": {"value": None}}}
            packet = uploader._build_packet(data)
        assert packet is not None
        assert "t..." in packet

    def test_temperature_present_with_mute_emits_sentinel(self, cwop_db):
        _set_mute("outdoor_temperature", True)
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            packet = uploader._build_packet(_SAMPLE_BROADCAST)
        assert packet is not None
        assert "t..." in packet

    def test_rain_query_skipped_when_rain_hour_muted(self, cwop_db):
        _set_mute("rain_hour", True)
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0) as m:
            uploader.reload_config()
            uploader._build_packet(_SAMPLE_BROADCAST)
            # rain_24h still queried, rain_hour skipped → one call, not two
            assert m.call_count == 1
            assert m.call_args.args == (24,)

    def test_no_mutes_emits_full_packet(self, cwop_db):
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            packet = uploader._build_packet(_SAMPLE_BROADCAST)
        assert packet is not None
        # Spot-check: temp, humidity, baro all rendered numerically.
        assert "t072" in packet
        assert "h50" in packet
        assert "_270/010" in packet
        # No sentinels present anywhere in the WX section.
        for sentinel in _SENTINEL_BY_CHANNEL.values():
            assert sentinel not in packet, (
                f"unexpected sentinel {sentinel!r} in clean packet {packet!r}"
            )

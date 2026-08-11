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


def test_mute_channels_canonical_order():
    # Pins the wire-facing channel list.  Adding a channel is fine; changing
    # its position or renaming it silently would migrate every operator's
    # stored mutes onto the wrong key.  The Settings.tsx grid, the AppShell
    # banner labels, and the WU/CWOP drop tables all read this order.
    assert MUTE_CHANNELS == (
        "outdoor_temperature",
        "outdoor_humidity",
        "wind_speed",
        "wind_direction",
        "wind_gust",
        "barometer",
        "rain_daily",
        "rain_hour",
        "rain_24h",
        "solar_radiation",
        "uv_index",
    )


def test_every_mute_channel_has_a_config_default():
    """Every MUTE_CHANNELS entry needs a corresponding channel_mute_<c> key
    in _DEFAULTS.

    The two contracts are joined at the hip.  ``load_muted_channels`` honors
    any saved row keyed on ``channel_mute_<channel>`` for a channel in
    MUTE_CHANNELS, but ``GET /api/config`` only emits keys present in
    _DEFAULTS — so a channel that made it into MUTE_CHANNELS without a
    matching _DEFAULTS row saves fine, mutes uploads fine, and then the
    Settings checkbox reads unchecked on the next reload.  Invisible mute,
    no reliable UI clear.  Codex caught this shape on the solar/UV PR when
    the checkbox was added without the default; this test prevents the
    next channel addition from repeating it.
    """
    from app.api.config import _DEFAULTS

    for channel in MUTE_CHANNELS:
        key = mute_key(channel)
        assert key in _DEFAULTS, (
            f"channel {channel!r} is in MUTE_CHANNELS but its config key "
            f"{key!r} is missing from _DEFAULTS — GET /api/config will drop "
            f"any saved mute row and the Settings UI will read unchecked."
        )
        # And the default must be a plain False (not None, not a truthy
        # string).  Anything else means a saved-false-round-trip renders
        # the checkbox as something other than unchecked.
        assert _DEFAULTS[key] is False, (
            f"_DEFAULTS[{key!r}] should be False, got {_DEFAULTS[key]!r}"
        )


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
    "solar_radiation": {"value": 423, "unit": "W/m²"},
    "uv_index": {"value": 5.2, "unit": ""},
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
    "solar_radiation": "L...",
}


# APRS101 §12 has no UV field, so muting uv_index is a no-op on the CWOP
# path.  The parametrize skips it; a dedicated test below asserts the
# no-op explicitly rather than letting the absence itself carry meaning.
_CWOP_APRS_CHANNELS = tuple(c for c in CWOP_MUTE_CHANNELS if c != "uv_index")


class TestBuildPacketMute:
    """Each mute key swaps the corresponding APRS field for its sentinel."""

    @pytest.mark.parametrize("channel", list(_CWOP_APRS_CHANNELS))
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
        # Spot-check: temp, humidity, baro, solar all rendered numerically.
        assert "t072" in packet
        assert "h50" in packet
        assert "_270/010" in packet
        assert "L423" in packet
        # No sentinels present anywhere in the WX section.
        for sentinel in _SENTINEL_BY_CHANNEL.values():
            assert sentinel not in packet, (
                f"unexpected sentinel {sentinel!r} in clean packet {packet!r}"
            )

    def test_uv_mute_is_a_noop_on_cwop(self, cwop_db):
        """Documents (and pins) that muting UV does nothing to the CWOP
        packet, because APRS101 §12 has no UV field.  The mute channel
        still exists to drop UV from Weather Underground — see wunderground
        tests — but must not accidentally affect the APRS output.
        """
        _set_mute("uv_index", True)
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            muted_packet = uploader._build_packet(_SAMPLE_BROADCAST)

        # And with no UV mute, for direct comparison.
        db = SessionLocal()
        db.query(StationConfigModel).filter_by(key=_mute_key("uv_index")).delete()
        db.commit()
        db.close()
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            clean_packet = uploader._build_packet(_SAMPLE_BROADCAST)

        # Timestamps in the two packets can differ; strip the 8-byte APRS
        # timestamp group (``@DDHHMMz``) and compare everything from the
        # latitude onward.
        assert muted_packet is not None and clean_packet is not None
        assert muted_packet[8:] == clean_packet[8:], (
            f"UV mute changed the APRS packet body:\n  muted:  {muted_packet}\n  clean:  {clean_packet}"
        )
        assert "L423" in muted_packet    # solar still there
        assert "L..." not in muted_packet

    def test_solar_missing_emits_sentinel(self, cwop_db):
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            data = {**_SAMPLE_BROADCAST, "solar_radiation": {"value": None, "unit": "W/m²"}}
            packet = uploader._build_packet(data)
        assert packet is not None
        assert "L..." in packet

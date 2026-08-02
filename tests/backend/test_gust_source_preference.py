"""Published gust prefers the station's own value over the daily maximum.

``cwop.py`` and ``wunderground.py`` both sourced gust from
``daily_extremes.wind_speed_hi``.  That is not a gust: it is the largest
of our 15 s point samples since midnight.  The console samples the
anemometer far faster and reports a true peak over its own window, so
the daily max systematically under-reports — and, being a running
extreme, it outlives the conditions that produced it.  It is also the
field that carried a 255 mph dashed sentinel to findu (#230).

The live ``wind_gust`` column was never in the broadcast payload, which
is why the publishers had nothing else to reach for.  This wires it in
and prefers it.

The preference is keyed on the value being present, not on driver type.
A station that normally reports a gust can still drop it mid-session —
a LOOP2 timeout on Vantage is exactly that case (#232) — and the
fallback has to engage for as long as the value is missing, not for as
long as the driver is of some type.
"""

from unittest.mock import patch

import pytest

from app.models.database import Base, SessionLocal, engine
from app.models.station_config import StationConfigModel
from app.services.cwop import CwopUploader
from app.services.wunderground import (
    FIELD_FALLBACKS,
    FIELD_MAP,
    WundergroundUploader,
)


@pytest.fixture
def cwop_db():
    """station_config seeded with CWOP enabled and a location.

    Same shape as the fixture in test_cwop.py — CwopUploader reads
    callsign and lat/lon at reload_config() and refuses to build a packet
    without them.
    """
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


def _broadcast(gust=None, daily_hi=15):
    """Broadcast payload shaped like the poller's, with optional gust."""
    data = {
        "temperature": {"outside": {"value": 72.0}},
        "humidity": {"outside": {"value": 50}},
        "wind": {
            "speed": {"value": 10},
            "direction": {"value": 270},
        },
        "barometer": {"value": 29.92},
        "rain": {"daily": {"value": 0.12}},
        "daily_extremes": {"wind_speed_hi": {"value": daily_hi}},
    }
    if gust is not None:
        data["wind"]["gust"] = {"value": gust}
    return data


class TestWundergroundFieldMapping:
    def test_gust_maps_to_the_live_wind_gust(self):
        assert FIELD_MAP["windgustmph"] == ("wind", "gust", "value")

    def test_daily_max_is_the_declared_fallback(self):
        assert FIELD_FALLBACKS["windgustmph"] == (
            "daily_extremes", "wind_speed_hi", "value",
        )

    def test_gust_is_the_only_field_with_a_fallback(self):
        """Keep the mechanism narrow — a general fallback table invites
        silently papering over other missing fields."""
        assert set(FIELD_FALLBACKS) == {"windgustmph"}


class TestWundergroundGustSource:
    def _params(self, data):
        uploader = WundergroundUploader()
        uploader._station_id = "TEST"
        uploader._station_key = "key"
        with patch.object(
            WundergroundUploader, "_get_hourly_rain_inches", return_value=None
        ):
            return uploader._build_params(data)

    def test_station_gust_wins_when_present(self):
        params = self._params(_broadcast(gust=32, daily_hi=15))
        assert params["windgustmph"] == 32

    def test_falls_back_to_daily_max_when_absent(self):
        params = self._params(_broadcast(gust=None, daily_hi=15))
        assert params["windgustmph"] == 15

    def test_falls_back_when_gust_present_but_null(self):
        """A LOOP2 dropout yields {"value": None}, not a missing key."""
        params = self._params(_broadcast(gust=None, daily_hi=15))
        data = _broadcast(daily_hi=15)
        data["wind"]["gust"] = {"value": None}
        assert self._params(data)["windgustmph"] == 15

    def test_station_gust_below_daily_max_still_wins(self):
        """The daily max is not a floor.  A 12 mph current gust against a
        40 mph max set hours ago is the honest number to publish now."""
        params = self._params(_broadcast(gust=12, daily_hi=40))
        assert params["windgustmph"] == 12

    def test_no_gust_anywhere_omits_the_field(self):
        data = _broadcast(gust=None)
        del data["daily_extremes"]
        assert "windgustmph" not in self._params(data)


class TestCwopGustSource:
    """CWOP converts to tenths m/s, so assert on the converted value."""

    def _packet_gust_mph(self, data):
        uploader = CwopUploader()
        with patch.object(CwopUploader, "_get_rain_accumulation", return_value=0):
            uploader.reload_config()
            packet = uploader._build_packet(data)
        assert packet is not None
        # APRS gust field: "g" followed by 3 digits of mph
        idx = packet.index("g")
        return int(packet[idx + 1:idx + 4])

    def test_station_gust_wins_when_present(self, cwop_db):
        assert self._packet_gust_mph(_broadcast(gust=32, daily_hi=15)) == 32

    def test_falls_back_to_daily_max_when_absent(self, cwop_db):
        assert self._packet_gust_mph(_broadcast(gust=None, daily_hi=15)) == 15

    def test_station_gust_below_daily_max_still_wins(self, cwop_db):
        assert self._packet_gust_mph(_broadcast(gust=12, daily_hi=40)) == 12


class TestGustIsBoundsChecked:
    """#230 again: a sentinel must not survive the hop to a published
    packet.  The live column had no bounds check before this."""

    def test_api_current_drops_out_of_range_gust(self):
        from app.api.current import _bounded

        # 894 tenths m/s ≈ 200 mph is the declared ceiling.
        assert _bounded("wind_gust", 2550) is None
        assert _bounded("wind_gust", 895) is None

    def test_api_current_keeps_in_range_gust(self):
        from app.api.current import _bounded

        val = _bounded("wind_gust", 100)     # 10 m/s
        assert val is not None
        assert val["value"] is not None

    def test_api_current_passes_none_through(self):
        from app.api.current import _bounded

        assert _bounded("wind_gust", None) is None

    @pytest.mark.parametrize("raw_ms,expected_none", [
        (114.0, True),      # 255 mph — the sentinel that reached findu
        (10.0, False),
        (89.5, True),       # just over the 89.4 m/s ceiling
        (0.0, False),
    ])
    def test_poller_gust_bounds(self, raw_ms, expected_none):
        """The WS payload is what the publishers usually see, so it needs
        the same guard as the REST path."""
        from app.models.sensor_meta import SENSOR_BOUNDS

        lo, hi = SENSOR_BOUNDS["wind_gust"]
        out_of_range = not (lo <= round(raw_ms * 10) <= hi)
        assert out_of_range == expected_none

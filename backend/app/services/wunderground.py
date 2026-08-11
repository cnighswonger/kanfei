"""Weather Underground Personal Weather Station upload service.

Periodically uploads sensor readings to WU using their PWS Upload Protocol.
Called on every poller broadcast; internally rate-limits to the configured
upload interval.  Configuration is read from the station_config database
table so changes made through the Settings UI take effect immediately.

Reference: https://support.weather.com/s/article/PWS-Upload-Protocol
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import func

from ..models.database import SessionLocal
from ..models.station_config import StationConfigModel
from .channel_mute import load_muted_channels

logger = logging.getLogger(__name__)

WU_URL = "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"
REQUEST_TIMEOUT = 10.0
MAX_CONSECUTIVE_ERRORS = 5
MAX_BACKOFF_INTERVAL = 300  # 5 minutes

# Map of WU parameter name -> nested dict path in the poller broadcast data.
FIELD_MAP: dict[str, tuple[str, ...]] = {
    "tempf":            ("temperature", "outside", "value"),
    "indoortempf":      ("temperature", "inside", "value"),
    "humidity":         ("humidity", "outside", "value"),
    "indoorhumidity":   ("humidity", "inside", "value"),
    "windspeedmph":     ("wind", "speed", "value"),
    "windgustmph":      ("wind", "gust", "value"),
    "winddir":          ("wind", "direction", "value"),
    "windchillf":       ("derived", "wind_chill", "value"),
    "baromin":          ("barometer", "value"),
    "dailyrainin":      ("rain", "daily", "value"),
    "yearrainin":       ("rain", "yearly", "value"),
    "rainratein":       ("rain", "rate", "value"),
    "dewptf":           ("derived", "dew_point", "value"),
    "heatindexf":       ("derived", "heat_index", "value"),
    "solarradiation":   ("solar_radiation", "value"),
    "UV":               ("uv_index", "value"),
}

# Secondary paths, tried only when the FIELD_MAP path yields nothing.
#
# Gust is the one field with a meaningful fallback.  The station's own
# gust is a true peak over the console's sampling window; the daily
# maximum is the largest of our 15 s point samples, which misses peaks
# between polls and under-reports.  Stations that report a gust
# (Vantage with LOOP2, Ecowitt, Tempest, WeatherLink Live) now publish
# it; those that never do (legacy Monitor II, Ambient) keep the old
# behaviour.
#
# Keyed on the value being absent rather than on driver type, so a
# station that normally reports a gust but drops it mid-session — a
# LOOP2 timeout on Vantage, say — falls back for exactly as long as the
# value is missing.
FIELD_FALLBACKS: dict[str, tuple[str, ...]] = {
    "windgustmph":      ("daily_extremes", "wind_speed_hi", "value"),
}


# When a channel is muted (issue #162), drop its directly-mapped WU field
# AND any derived field computed from the same sensor — sending a derived
# value based on known-bad data defeats the purpose of muting.  WU has no
# 24h-rain field, so ``rain_24h`` is a no-op for this service.
#
# ``yearrainin`` and ``rainratein`` are WU-only fields with no CWOP analog;
# both come from the same physical rain gauge counter as ``dailyrainin``.
# If the operator mutes ``rain_daily`` the gauge itself is the thing under
# repair, so the cumulative and rate views of the same broken sensor must
# also drop out.
_DROP_BY_CHANNEL: dict[str, tuple[str, ...]] = {
    "outdoor_temperature": ("tempf", "windchillf", "heatindexf", "dewptf"),
    "outdoor_humidity":    ("humidity", "heatindexf", "dewptf"),
    "wind_speed":          ("windspeedmph", "windchillf"),
    "wind_direction":      ("winddir",),
    "wind_gust":           ("windgustmph",),
    "barometer":           ("baromin",),
    "rain_daily":          ("dailyrainin", "yearrainin", "rainratein"),
    "rain_hour":           ("rainin",),
    "rain_24h":            (),
    "solar_radiation":     ("solarradiation",),
    "uv_index":            ("UV",),
}


def _extract(data: dict, path: tuple[str, ...]) -> Optional[Any]:
    """Walk a nested dict by key path, returning None if any key is missing."""
    obj: Any = data
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
        if obj is None:
            return None
    return obj


class WundergroundUploader:
    """Uploads sensor data to Weather Underground PWS API."""

    def __init__(self) -> None:
        self._station_id: str = ""
        self._station_key: str = ""
        self._enabled: bool = False
        self._upload_interval: int = 60
        self._last_upload: float = 0.0
        self._consecutive_errors: int = 0
        self._effective_interval: int = 60
        self._muted: frozenset[str] = frozenset()

    def reload_config(self) -> None:
        """Read WU config from the station_config database table."""
        db = SessionLocal()
        try:
            rows = (
                db.query(StationConfigModel)
                .filter(StationConfigModel.key.in_([
                    "wu_enabled", "wu_station_id",
                    "wu_station_key", "wu_upload_interval",
                ]))
                .all()
            )
            cfg = {r.key: r.value for r in rows}
            self._enabled = cfg.get("wu_enabled", "false").lower() == "true"
            self._station_id = cfg.get("wu_station_id", "")
            self._station_key = cfg.get("wu_station_key", "")
            try:
                self._upload_interval = int(cfg.get("wu_upload_interval", "60"))
            except (ValueError, TypeError):
                self._upload_interval = 60
            # Reset effective interval when config is reloaded
            self._effective_interval = self._upload_interval
            self._muted = load_muted_channels(db)
        except Exception as exc:
            logger.error("Failed to load WU config: %s", exc)
        finally:
            db.close()

    async def maybe_upload(self, data: dict) -> None:
        """Called on every sensor broadcast. Upload if enabled and interval elapsed."""
        # Re-read config each cycle so Settings changes take effect immediately
        self.reload_config()

        if not self._enabled or not self._station_id or not self._station_key:
            return

        now = time.monotonic()
        if now - self._last_upload < self._effective_interval:
            return

        await self._do_upload(data)

    async def _do_upload(self, data: dict) -> None:
        """Build WU query params and send HTTP GET."""
        params = self._build_params(data)

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                resp = await client.get(WU_URL, params=params)
                body = resp.text.strip()

            if body.lower().startswith("success"):
                self._last_upload = time.monotonic()
                self._consecutive_errors = 0
                self._effective_interval = self._upload_interval
                logger.debug("WU upload OK")
            else:
                self._consecutive_errors += 1
                logger.warning("WU upload rejected: %s", body)
                self._apply_backoff()

        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            self._consecutive_errors += 1
            logger.warning("WU upload failed: %s", exc)
            self._apply_backoff()
        except Exception as exc:
            self._consecutive_errors += 1
            logger.error("WU upload unexpected error: %s", exc)
            self._apply_backoff()

    def _apply_backoff(self) -> None:
        """Double the effective interval after repeated failures."""
        if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            self._effective_interval = min(
                self._effective_interval * 2,
                MAX_BACKOFF_INTERVAL,
            )
            logger.error(
                "WU upload: %d consecutive errors, backing off to %ds",
                self._consecutive_errors, self._effective_interval,
            )

    def _build_params(self, data: dict) -> dict:
        """Map sensor broadcast data to WU query parameters.

        Channels named in ``self._muted`` (and any derived WU field
        computed from the same sensor) are dropped from the upload —
        WU's protocol treats an absent parameter as "no reading," which
        is the desired behaviour while a sensor is out of service.
        """
        params: dict[str, Any] = {
            "ID": self._station_id,
            "PASSWORD": self._station_key,
            "dateutc": "now",
            "action": "updateraw",
            "softwaretype": "kanfei",
        }

        for wu_param, path in FIELD_MAP.items():
            value = _extract(data, path)
            if value is None:
                fallback = FIELD_FALLBACKS.get(wu_param)
                if fallback is not None:
                    value = _extract(data, fallback)
            if value is not None:
                params[wu_param] = value

        # Hourly rain — not in broadcast, compute from DB.  Skip the
        # query when ``rain_hour`` is muted to save a round-trip.
        if "rain_hour" not in self._muted:
            rain_hour = self._get_hourly_rain_inches()
            if rain_hour is not None:
                params["rainin"] = rain_hour

        # Drop muted fields and any derived fields that depend on them.
        for channel in self._muted:
            for field in _DROP_BY_CHANNEL.get(channel, ()):
                params.pop(field, None)

        return params

    @staticmethod
    def _get_hourly_rain_inches() -> Optional[float]:
        """Query rain accumulation over the last hour from sensor_readings.

        Returns rain in inches (WU expected unit). DB stores tenths of mm.
        """
        from ..models.sensor_reading import SensorReadingModel
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            S = SensorReadingModel

            current = (
                db.query(S.rain_total)
                .filter(S.rain_total.isnot(None))
                .order_by(S.timestamp.desc())
                .first()
            )
            if current is None or current[0] is None:
                return None

            oldest = (
                db.query(S.rain_total)
                .filter(S.timestamp >= cutoff, S.rain_total.isnot(None))
                .order_by(S.timestamp.asc())
                .first()
            )
            if oldest is None or oldest[0] is None:
                return None

            delta_tenths_mm = current[0] - oldest[0]
            if delta_tenths_mm < 0:
                return 0.0  # counter reset
            # Convert tenths mm → inches
            return round(delta_tenths_mm / 10.0 / 25.4, 2)
        finally:
            db.close()

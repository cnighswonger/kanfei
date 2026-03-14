"""Weather Underground Personal Weather Station upload service.

Periodically uploads sensor readings to WU using their PWS Upload Protocol.
Called on every poller broadcast; internally rate-limits to the configured
upload interval.  Configuration is read from the station_config database
table so changes made through the Settings UI take effect immediately.

Reference: https://support.weather.com/s/article/PWS-Upload-Protocol
"""

import logging
import time
from typing import Any, Optional

import httpx

from ..models.database import SessionLocal
from ..models.station_config import StationConfigModel

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
    "winddir":          ("wind", "direction", "value"),
    "baromin":          ("barometer", "value"),
    "dailyrainin":      ("rain", "daily", "value"),
    "yearrainin":       ("rain", "yearly", "value"),
    "dewptf":           ("derived", "dew_point", "value"),
    "solarradiation":   ("solar_radiation", "value"),
    "UV":               ("uv_index", "value"),
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
        params = self._build_params(self._station_id, self._station_key, data)

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

    @staticmethod
    def _build_params(station_id: str, station_key: str, data: dict) -> dict:
        """Map sensor broadcast data to WU query parameters."""
        params: dict[str, Any] = {
            "ID": station_id,
            "PASSWORD": station_key,
            "dateutc": "now",
            "action": "updateraw",
            "softwaretype": "kanfei",
        }

        for wu_param, path in FIELD_MAP.items():
            value = _extract(data, path)
            if value is not None:
                params[wu_param] = value

        return params

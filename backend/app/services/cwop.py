"""CWOP (Citizen Weather Observer Program) upload service via APRS-IS.

Periodically uploads sensor readings to CWOP/APRS-IS servers using the
APRS weather packet format over TCP.  Called on every poller broadcast;
internally rate-limits to the configured interval (default 5 minutes).

Configuration is read from the station_config database table so changes
made through the Settings UI take effect immediately.

References:
    http://www.wxqa.com/SIGN-UP.html
    http://www.aprs.org/doc/APRS101.PDF  (Chapter 12 - Weather)
"""

import asyncio
import logging
import time
from typing import Any, Optional

from ..models.database import SessionLocal
from ..models.station_config import StationConfigModel
from ..output.aprs import APRSWeatherPacket

logger = logging.getLogger(__name__)

APRS_IS_SERVERS = [
    ("cwop.aprs.net", 14580),
    ("rotate.aprs2.net", 14580),
]
CONNECT_TIMEOUT = 10.0
MAX_CONSECUTIVE_ERRORS = 5
MAX_BACKOFF_INTERVAL = 1800  # 30 minutes

# CWOP callsigns use these prefixes and always authenticate with -1.
_CWOP_PREFIXES = ("CW", "DW", "EW")


def aprs_passcode(callsign: str) -> str:
    """Compute the APRS-IS passcode from a callsign.

    CWOP callsigns (CW/DW/EW prefixes) always use ``-1``.
    Ham callsigns use the standard APRS-IS hash algorithm.

    Reference: http://www.aprs-is.net/Connecting.aspx
    """
    call = callsign.strip().upper()
    if not call:
        return "-1"
    # CWOP stations don't need authentication.
    if any(call.startswith(p) for p in _CWOP_PREFIXES):
        return "-1"
    # Strip SSID (e.g. N0CALL-13 → N0CALL) for the hash.
    base = call.split("-")[0]
    h = 0x73E2
    for i in range(0, len(base) - 1, 2):
        h ^= ord(base[i]) << 8
        h ^= ord(base[i + 1])
    if len(base) % 2 == 1:
        h ^= ord(base[-1]) << 8
    return str(h & 0x7FFF)


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


class CwopUploader:
    """Uploads sensor data to CWOP via APRS-IS TCP connection."""

    def __init__(self) -> None:
        self._callsign: str = ""
        self._passcode: str = "-1"
        self._enabled: bool = False
        self._upload_interval: int = 300
        self._latitude: float = 0.0
        self._longitude: float = 0.0
        self._last_upload: float = 0.0
        self._consecutive_errors: int = 0
        self._effective_interval: int = 300

    def reload_config(self) -> None:
        """Read CWOP config from the station_config database table."""
        db = SessionLocal()
        try:
            rows = (
                db.query(StationConfigModel)
                .filter(StationConfigModel.key.in_([
                    "cwop_enabled", "cwop_callsign",
                    "cwop_upload_interval",
                    "latitude", "longitude",
                ]))
                .all()
            )
            cfg = {r.key: r.value for r in rows}
            self._enabled = cfg.get("cwop_enabled", "false").lower() == "true"
            self._callsign = cfg.get("cwop_callsign", "").strip().upper()
            self._passcode = aprs_passcode(self._callsign)
            try:
                self._upload_interval = max(300, int(cfg.get("cwop_upload_interval", "300")))
            except (ValueError, TypeError):
                self._upload_interval = 300
            try:
                self._latitude = float(cfg.get("latitude", "0"))
                self._longitude = float(cfg.get("longitude", "0"))
            except (ValueError, TypeError):
                self._latitude = 0.0
                self._longitude = 0.0
            self._effective_interval = self._upload_interval
        except Exception as exc:
            logger.error("Failed to load CWOP config: %s", exc)
        finally:
            db.close()

    async def maybe_upload(self, data: dict) -> None:
        """Called on every sensor broadcast. Upload if enabled and interval elapsed."""
        self.reload_config()

        if not self._enabled or not self._callsign:
            return

        if self._latitude == 0.0 and self._longitude == 0.0:
            return

        now = time.monotonic()
        if now - self._last_upload < self._effective_interval:
            return

        await self._do_upload(data)

    async def _do_upload(self, data: dict) -> None:
        """Build APRS packet and send via TCP to APRS-IS."""
        packet = self._build_packet(data)
        if packet is None:
            return

        login_line = (
            f"user {self._callsign} pass {self._passcode} "
            f"vers kanfei 1.0\r\n"
        )
        packet_line = (
            f"{self._callsign}>APRS,TCPIP*:{packet}\r\n"
        )

        for host, port in APRS_IS_SERVERS:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=CONNECT_TIMEOUT,
                )
                try:
                    # Read server banner
                    await asyncio.wait_for(reader.readline(), timeout=CONNECT_TIMEOUT)

                    # Send login
                    writer.write(login_line.encode())
                    await writer.drain()

                    # Read login response
                    response = await asyncio.wait_for(
                        reader.readline(), timeout=CONNECT_TIMEOUT,
                    )
                    resp_text = response.decode(errors="replace").strip()
                    logger.debug("CWOP login response: %s", resp_text)

                    # Send weather packet
                    writer.write(packet_line.encode())
                    await writer.drain()

                    # Brief pause to let server process before disconnect
                    await asyncio.sleep(0.5)
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass

                self._last_upload = time.monotonic()
                self._consecutive_errors = 0
                self._effective_interval = self._upload_interval
                logger.info("CWOP upload OK (%s:%d)", host, port)
                return

            except (OSError, asyncio.TimeoutError) as exc:
                logger.warning("CWOP connection to %s:%d failed: %s", host, port, exc)
                continue
            except Exception as exc:
                logger.error("CWOP unexpected error (%s:%d): %s", host, port, exc)
                continue

        # All servers failed
        self._consecutive_errors += 1
        logger.warning("CWOP upload failed on all servers")
        self._apply_backoff()

    def _apply_backoff(self) -> None:
        """Double the effective interval after repeated failures."""
        if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            self._effective_interval = min(
                self._effective_interval * 2,
                MAX_BACKOFF_INTERVAL,
            )
            logger.error(
                "CWOP upload: %d consecutive errors, backing off to %ds",
                self._consecutive_errors, self._effective_interval,
            )

    def _build_packet(self, data: dict) -> Optional[str]:
        """Extract sensor values from broadcast data and format APRS packet."""
        temp_f = _extract(data, ("temperature", "outside", "value"))
        if temp_f is None:
            return None

        humidity = _extract(data, ("humidity", "outside", "value"))
        wind_speed = _extract(data, ("wind", "speed", "value"))
        wind_dir = _extract(data, ("wind", "direction", "value"))
        baro_inhg = _extract(data, ("barometer", "value"))
        rain_daily = _extract(data, ("rain", "daily", "value"))

        # Wind gust: today's peak wind speed from daily extremes
        wind_gust = _extract(data, ("daily_extremes", "wind_speed_hi", "value"))

        pkt = APRSWeatherPacket(
            callsign=self._callsign,
            latitude=self._latitude,
            longitude=self._longitude,
            wind_dir_deg=int(wind_dir) if wind_dir is not None else None,
            wind_speed_mph=int(wind_speed) if wind_speed is not None else 0,
            wind_gust_mph=int(wind_gust) if wind_gust is not None else 0,
            temp_tenths_f=int(temp_f * 10),
            rain_hour_hundredths_in=0,
            rain_24h_hundredths_in=0,
            rain_midnight_hundredths_in=int(rain_daily * 100) if rain_daily is not None else 0,
            humidity_pct=int(humidity) if humidity is not None else 0,
            barometer_thousandths_inhg=int(baro_inhg * 1000) if baro_inhg is not None else 29920,
        )
        return pkt.format_packet()

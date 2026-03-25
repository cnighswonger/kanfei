"""WeatherFlow Tempest station driver.

Passive UDP listener — the Tempest hub broadcasts JSON datagrams on port
50222.  The driver binds a socket, caches incoming observations, and returns
the latest snapshot when polled.

Key differences from serial/TCP drivers:
  - No request/response — data arrives unsolicited
  - poll() returns cached data, never blocks on I/O
  - connect() binds the UDP socket; disconnect() closes it
  - Rain daily/yearly tracked internally (hub provides per-interval only)
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ..base import StationDriver, SensorSnapshot, HardwareInfo
from .constants import (
    MSG_OBS_ST, MSG_OBS_AIR, MSG_OBS_SKY, MSG_RAPID_WIND,
    MSG_HUB_STATUS, MSG_DEVICE_STATUS, MSG_EVT_PRECIP, MSG_EVT_STRIKE,
    STALE_WARNING_SECS, STALE_DISCONNECT_SECS,
)
from .protocol import create_listener
from .sensors import (
    parse_obs_st, parse_obs_air, parse_obs_sky, parse_rapid_wind,
    build_snapshot,
)

logger = logging.getLogger(__name__)


class TempestDriver(StationDriver):
    """WeatherFlow Tempest driver via local UDP broadcast."""

    def __init__(
        self,
        hub_sn: str = "",
        elevation_ft: float = 0.0,
        timezone_name: str = "",
    ) -> None:
        self._hub_sn_filter = hub_sn
        self._elevation_m = elevation_ft * 0.3048  # store as meters for SI
        self._tz_name = timezone_name
        self._connected = False
        self._stop_requested = False

        # UDP transport
        self._transport = None
        self._protocol = None

        # Cached observation data
        self._last_obs: Optional[dict[str, Any]] = None
        self._last_rapid_wind: Optional[dict[str, Any]] = None
        self._last_obs_time: float = 0.0

        # Hub/device info (populated from status messages)
        self._hub_serial: str = ""
        self._hub_firmware: str = ""
        self._device_serial: str = ""

        # Rain tracking — Tempest reports per-interval accumulation only
        self._rain_daily_mm: float = 0.0
        self._rain_yearly_mm: float = 0.0
        self._rain_rate_mm_hr: float = 0.0
        self._current_day: int = 0   # day-of-year for midnight reset

    # ---- StationDriver interface ----

    async def connect(self) -> None:
        """Bind the UDP socket and start listening."""
        self._transport, self._protocol = await create_listener(
            hub_sn=self._hub_sn_filter,
            on_message=self._on_message,
        )
        self._connected = True

        # Initialise day tracking for rain reset
        now = self._local_now()
        self._current_day = now.timetuple().tm_yday

        logger.info(
            "Tempest driver listening on UDP %d (hub filter: %s)",
            self._transport.get_extra_info("sockname", ("?", 0))[1],
            self._hub_sn_filter or "any",
        )

    async def disconnect(self) -> None:
        """Close the UDP socket."""
        if self._protocol:
            self._protocol.close()
        self._transport = None
        self._protocol = None
        self._connected = False
        logger.info("Tempest driver disconnected")

    async def poll(self) -> Optional[SensorSnapshot]:
        """Return the latest cached snapshot, or None if no data yet."""
        if self._last_obs is None:
            return None

        # Staleness check
        age = time.time() - self._last_obs_time
        if age > STALE_DISCONNECT_SECS:
            if self._connected:
                logger.warning(
                    "No Tempest observation for %.0fs — marking disconnected", age,
                )
                self._connected = False
            return None
        elif age > STALE_WARNING_SECS:
            logger.warning("Tempest observation is %.0fs old", age)

        return build_snapshot(
            self._last_obs,
            self._last_rapid_wind,
            rain_daily_mm=self._rain_daily_mm,
            rain_yearly_mm=self._rain_yearly_mm,
            rain_rate_mm_hr=self._rain_rate_mm_hr,
            elevation_m=self._elevation_m,
        )

    async def detect_hardware(self) -> HardwareInfo:
        return HardwareInfo(
            name=self.station_name,
            model_code=0,
            capabilities=self.capabilities,
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def station_name(self) -> str:
        sn = self._hub_serial or self._hub_sn_filter or "unknown"
        fw = f" (fw {self._hub_firmware})" if self._hub_firmware else ""
        return f"WeatherFlow Tempest {sn}{fw}"

    @property
    def capabilities(self) -> set[str]:
        return set()

    def request_stop(self) -> None:
        self._stop_requested = True

    # ---- Rain state persistence ----

    @property
    def rain_state(self) -> dict[str, Any]:
        """Return rain tracking state for persistence."""
        return {
            "rain_daily_mm": self._rain_daily_mm,
            "rain_yearly_mm": self._rain_yearly_mm,
            "rain_rate_mm_hr": self._rain_rate_mm_hr,
            "current_day": self._current_day,
        }

    def restore_rain_state(self, state: dict[str, Any]) -> None:
        """Restore rain tracking state from a previous run."""
        self._rain_daily_mm = state.get("rain_daily_mm", 0.0)
        self._rain_yearly_mm = state.get("rain_yearly_mm", 0.0)
        self._rain_rate_mm_hr = state.get("rain_rate_mm_hr", 0.0)
        self._current_day = state.get("current_day", 0)
        logger.info(
            "Restored Tempest rain state: daily=%.1fmm yearly=%.1fmm",
            self._rain_daily_mm, self._rain_yearly_mm,
        )

    # ---- Internal message dispatch ----

    def _on_message(self, msg: dict[str, Any]) -> None:
        """Dispatch incoming UDP datagram by message type."""
        msg_type = msg.get("type", "")

        if msg_type == MSG_OBS_ST:
            self._handle_obs_st(msg)
        elif msg_type == MSG_OBS_AIR:
            self._handle_obs_air(msg)
        elif msg_type == MSG_OBS_SKY:
            self._handle_obs_sky(msg)
        elif msg_type == MSG_RAPID_WIND:
            self._handle_rapid_wind(msg)
        elif msg_type == MSG_HUB_STATUS:
            self._handle_hub_status(msg)
        elif msg_type == MSG_DEVICE_STATUS:
            self._handle_device_status(msg)
        elif msg_type == MSG_EVT_PRECIP:
            logger.debug("Rain start event from %s", msg.get("serial_number", "?"))
        elif msg_type == MSG_EVT_STRIKE:
            self._handle_evt_strike(msg)

    def _handle_obs_st(self, msg: dict[str, Any]) -> None:
        """Handle Tempest all-in-one observation."""
        obs_arrays = msg.get("obs", [])
        if not obs_arrays:
            return
        # obs is array of arrays; typically one element
        obs = obs_arrays[0]
        parsed = parse_obs_st(obs)
        if not parsed:
            return

        self._last_obs = parsed
        self._last_obs_time = time.time()
        self._connected = True

        # Track hub/device info
        if not self._hub_serial:
            self._hub_serial = msg.get("hub_sn", "")
        if not self._device_serial:
            self._device_serial = msg.get("serial_number", "")

        # Rain tracking
        rain_mm = parsed.get("rain_accum_mm", 0.0)
        interval = parsed.get("report_interval_min", 1)
        self._update_rain(rain_mm, interval)

    def _handle_obs_air(self, msg: dict[str, Any]) -> None:
        """Handle legacy Air sensor observation."""
        obs_arrays = msg.get("obs", [])
        if not obs_arrays:
            return
        parsed = parse_obs_air(obs_arrays[0])
        if not parsed:
            return

        # Merge into last_obs — Air provides temp/humidity/pressure/lightning
        if self._last_obs is None:
            self._last_obs = parsed
        else:
            self._last_obs.update(parsed)
        self._last_obs_time = time.time()
        self._connected = True

        if not self._hub_serial:
            self._hub_serial = msg.get("hub_sn", "")

    def _handle_obs_sky(self, msg: dict[str, Any]) -> None:
        """Handle legacy Sky sensor observation."""
        obs_arrays = msg.get("obs", [])
        if not obs_arrays:
            return
        parsed = parse_obs_sky(obs_arrays[0])
        if not parsed:
            return

        # Merge into last_obs — Sky provides wind/rain/solar
        if self._last_obs is None:
            self._last_obs = parsed
        else:
            self._last_obs.update(parsed)
        self._last_obs_time = time.time()
        self._connected = True

        # Rain tracking
        rain_mm = parsed.get("rain_accum_mm", 0.0)
        interval = parsed.get("report_interval_min", 1)
        self._update_rain(rain_mm, interval)

    def _handle_rapid_wind(self, msg: dict[str, Any]) -> None:
        """Handle high-frequency wind update (every 3s)."""
        ob = msg.get("ob")  # Note: "ob" not "obs"
        if not ob:
            return
        parsed = parse_rapid_wind(ob)
        if parsed:
            self._last_rapid_wind = parsed

    def _handle_hub_status(self, msg: dict[str, Any]) -> None:
        """Update hub info from status message."""
        self._hub_serial = msg.get("serial_number", self._hub_serial)
        self._hub_firmware = str(msg.get("firmware_revision", self._hub_firmware))

    def _handle_device_status(self, msg: dict[str, Any]) -> None:
        """Update device info from status message."""
        sn = msg.get("serial_number", "")
        if sn and not self._device_serial:
            self._device_serial = sn

        status = msg.get("sensor_status", 0)
        if status != 0:
            logger.warning(
                "Tempest device %s sensor_status=0x%X (non-zero indicates fault)",
                sn, status,
            )

    def _handle_evt_strike(self, msg: dict[str, Any]) -> None:
        """Handle lightning strike event."""
        evt = msg.get("evt", [])
        if len(evt) >= 3:
            logger.info(
                "Lightning strike: distance=%skm energy=%s",
                evt[1], evt[2],
            )

    # ---- Rain tracking ----

    def _update_rain(self, rain_accum_mm: float, report_interval_min: float) -> None:
        """Update rain accumulation from an observation interval.

        rain_accum_mm is the rain that fell during this reporting interval
        (typically 1 minute), NOT a cumulative counter.
        """
        if report_interval_min <= 0:
            report_interval_min = 1

        # Compute rain rate: mm in interval → mm/hr
        self._rain_rate_mm_hr = (rain_accum_mm / report_interval_min) * 60.0

        # Check for midnight / year rollover before adding
        self._check_day_rollover()

        # Accumulate
        self._rain_daily_mm += rain_accum_mm
        self._rain_yearly_mm += rain_accum_mm

    def _check_day_rollover(self) -> None:
        """Reset daily rain at local midnight, yearly at Jan 1."""
        now = self._local_now()
        today = now.timetuple().tm_yday

        if today != self._current_day:
            logger.info(
                "Day rollover (day %d → %d): resetting daily rain (was %.1fmm)",
                self._current_day, today, self._rain_daily_mm,
            )
            self._rain_daily_mm = 0.0
            self._current_day = today

            # Year rollover: day went from 365/366 back to 1
            if today == 1:
                logger.info(
                    "Year rollover: resetting yearly rain (was %.1fmm)",
                    self._rain_yearly_mm,
                )
                self._rain_yearly_mm = 0.0

    def _local_now(self) -> datetime:
        """Get current local time using the configured timezone."""
        if self._tz_name:
            try:
                from zoneinfo import ZoneInfo
                return datetime.now(ZoneInfo(self._tz_name))
            except (ImportError, KeyError):
                pass
        return datetime.now().astimezone()

"""Ambient Weather / Fine Offset HTTP push station driver.

Passive HTTP receiver — weather stations push JSON data to a configured
endpoint on a regular interval (typically 60 seconds). The driver binds
a lightweight HTTP server, caches incoming data, and returns the latest
snapshot when polled.

Key differences from serial/TCP/UDP drivers:
  - No request/response — data arrives via HTTP push from the station
  - poll() returns cached data, never blocks on I/O
  - connect() starts the HTTP server; disconnect() stops it
  - Rain daily/yearly provided by station (no driver-side tracking)
  - Pressure is sea-level corrected by station (no altitude correction)
"""

import logging
import time
from typing import Any, Optional

from ..base import StationDriver, SensorSnapshot, HardwareInfo
from .constants import DEFAULT_HTTP_PORT, STALE_WARNING_SECS, STALE_DISCONNECT_SECS
from .receiver import create_http_receiver
from .sensors import parse_params, extract_station_info

logger = logging.getLogger(__name__)


class AmbientDriver(StationDriver):
    """Ambient Weather / Fine Offset driver via HTTP push."""

    def __init__(self, listen_port: int = DEFAULT_HTTP_PORT) -> None:
        self._listen_port = listen_port
        self._connected = False
        self._stop_requested = False

        # HTTP server
        self._server = None

        # Cached observation data
        self._last_snapshot: Optional[SensorSnapshot] = None
        self._last_data_time: float = 0.0

        # Station identification (populated from push parameters)
        self._station_model: str = ""
        self._station_firmware: str = ""
        self._station_id: str = ""

    # ---- StationDriver interface ----

    async def connect(self) -> None:
        """Start the HTTP receiver server."""
        self._server = await create_http_receiver(
            port=self._listen_port,
            on_data=self._on_data,
        )
        self._connected = True
        logger.info(
            "Ambient driver listening on HTTP port %d",
            self._listen_port,
        )

    async def disconnect(self) -> None:
        """Stop the HTTP receiver server."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        self._server = None
        self._connected = False
        logger.info("Ambient driver disconnected")

    async def poll(self) -> Optional[SensorSnapshot]:
        """Return the latest cached snapshot, or None if no data yet."""
        if self._last_snapshot is None:
            return None

        # Staleness check
        age = time.time() - self._last_data_time
        if age > STALE_DISCONNECT_SECS:
            if self._connected:
                logger.warning(
                    "No weather push for %.0fs — marking disconnected", age,
                )
                self._connected = False
            return None
        elif age > STALE_WARNING_SECS:
            logger.warning("Weather push data is %.0fs old", age)

        return self._last_snapshot

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
        model = self._station_model or "unknown"
        fw = f" (fw {self._station_firmware})" if self._station_firmware else ""
        return f"Ambient/Ecowitt {model}{fw}"

    @property
    def capabilities(self) -> set[str]:
        return set()

    def request_stop(self) -> None:
        self._stop_requested = True

    # ---- Internal data handler ----

    def _on_data(self, params: dict[str, str]) -> None:
        """Handle incoming HTTP push data from the station."""
        # Extract station identification
        info = extract_station_info(params)
        if "model" in info:
            self._station_model = info["model"]
        if "firmware" in info:
            self._station_firmware = info["firmware"]
        if "station_id" in info:
            self._station_id = info["station_id"]

        # Parse parameters into a snapshot
        self._last_snapshot = parse_params(params)
        self._last_data_time = time.time()
        self._connected = True

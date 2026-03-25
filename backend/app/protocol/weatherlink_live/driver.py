"""Davis WeatherLink Live (6100) station driver.

Pull-based HTTP driver — polls the WLL's local HTTP API for current
conditions.  Stateless: each poll is an independent HTTP GET.  No
persistent connection, no server, no listener.
"""

import logging
import time
from typing import Optional

from ..base import StationDriver, SensorSnapshot, HardwareInfo
from .constants import DEFAULT_HTTP_PORT, STALE_WARNING_SECS, STALE_DISCONNECT_SECS
from .http_client import fetch_current_conditions
from .sensors import parse_wll_response, extract_device_info

logger = logging.getLogger(__name__)


class WeatherLinkLiveDriver(StationDriver):
    """Davis WeatherLink Live (6100) driver via local HTTP API."""

    def __init__(self, ip: str, port: int = DEFAULT_HTTP_PORT) -> None:
        self._ip = ip
        self._port = port
        self._connected = False
        self._device_id: str = ""
        self._last_data_time: float = 0.0

    # ---- StationDriver interface ----

    async def connect(self) -> None:
        """Verify WLL is reachable by making a test HTTP GET."""
        response = await fetch_current_conditions(self._ip, self._port)
        if response is None:
            raise ConnectionError(
                f"Cannot reach WeatherLink Live at {self._ip}:{self._port}"
            )
        info = extract_device_info(response)
        self._device_id = info.get("did", "")
        self._connected = True
        self._last_data_time = time.time()
        logger.info(
            "WeatherLink Live connected at %s:%d (DID: %s)",
            self._ip, self._port, self._device_id,
        )

    async def disconnect(self) -> None:
        """No persistent connection to close."""
        self._connected = False
        logger.info("WeatherLink Live driver disconnected")

    async def poll(self) -> Optional[SensorSnapshot]:
        """HTTP GET current conditions and parse into SensorSnapshot."""
        response = await fetch_current_conditions(self._ip, self._port)
        if response is None:
            age = time.time() - self._last_data_time
            if age > STALE_DISCONNECT_SECS and self._connected:
                logger.warning(
                    "No WLL data for %.0fs — marking disconnected", age,
                )
                self._connected = False
            elif age > STALE_WARNING_SECS:
                logger.warning("WLL data is %.0fs stale", age)
            return None

        snapshot = parse_wll_response(response)
        if snapshot is not None:
            self._last_data_time = time.time()
            if not self._connected:
                logger.info("WLL connection restored")
                self._connected = True
        return snapshot

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
        did_suffix = f" ({self._device_id[-6:]})" if self._device_id else ""
        return f"WeatherLink Live{did_suffix}"

    @property
    def capabilities(self) -> set[str]:
        return set()

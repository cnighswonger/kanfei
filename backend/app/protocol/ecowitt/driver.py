"""Ecowitt / Fine Offset gateway driver.

Implements the StationDriver ABC for Ecowitt gateways (GW1000, GW1100,
GW2000) and Wi-Fi consoles via the TCP binary LAN API on port 45000.

Unlike the serial drivers, this is fully async — no threading locks
or ``run_in_executor`` needed.  Each command opens a fresh TCP connection.
"""

import logging
from typing import Optional

from ..base import (
    HardwareInfo,
    SensorSnapshot,
    StationDriver,
)
from .constants import (
    CMD_LIVEDATA,
    CMD_READ_FIRMWARE,
    CMD_READ_SSSS,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    MAX_RETRIES,
)
from .protocol import EcowittProtocolError, send_command
from .sensors import parse_live_data, raw_to_snapshot

logger = logging.getLogger(__name__)


class EcowittDriver(StationDriver):
    """Driver for Ecowitt/Fine Offset gateways and consoles.

    Communicates via the TCP binary protocol on port 45000.
    The gateway acts as a TCP server; we connect on demand for each
    command, so there is no persistent connection to manage.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._connected = False
        self._stop_requested = False
        self._firmware: str = ""
        self._model: str = ""
        self._frequency: str = ""

    # ---- StationDriver interface ----

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def station_name(self) -> str:
        if self._model:
            label = self._model
            if self._firmware:
                label += f" ({self._firmware})"
            return label
        if self._firmware:
            return f"Ecowitt ({self._firmware})"
        return "Ecowitt"

    @property
    def capabilities(self) -> set[str]:
        # Ecowitt gateways don't expose archive, calibration, clock sync,
        # rain reset, or hi/lows via the binary API.
        return set()

    def request_stop(self) -> None:
        self._stop_requested = True

    async def connect(self) -> None:
        """Validate connectivity by reading firmware and system info."""
        self._stop_requested = False
        await self._read_firmware()
        await self._read_system_info()
        self._connected = True
        logger.info(
            "Connected to %s at %s:%d",
            self.station_name, self._host, self._port,
        )

    async def disconnect(self) -> None:
        """Mark as disconnected.  No persistent connection to close."""
        self._connected = False
        logger.info("Ecowitt driver disconnected")

    async def detect_hardware(self) -> HardwareInfo:
        """Read model/firmware info from the gateway."""
        await self._read_firmware()
        return HardwareInfo(
            name=self.station_name,
            model_code=0,
            capabilities=self.capabilities,
        )

    async def poll(self) -> Optional[SensorSnapshot]:
        """Read live sensor data from the gateway."""
        if self._stop_requested:
            return None

        for attempt in range(MAX_RETRIES + 1):
            if self._stop_requested:
                return None
            try:
                payload = await send_command(
                    self._host, self._port, CMD_LIVEDATA,
                    timeout=self._timeout,
                )
                raw = parse_live_data(payload)
                snapshot = raw_to_snapshot(raw)
                self._connected = True
                return snapshot
            except (ConnectionError, TimeoutError, OSError) as exc:
                logger.warning(
                    "Ecowitt poll attempt %d/%d failed: %s",
                    attempt + 1, MAX_RETRIES + 1, exc,
                )
                self._connected = False
            except EcowittProtocolError as exc:
                logger.warning("Ecowitt protocol error: %s", exc)
                self._connected = False

        return None

    # ---- Internal helpers ----

    async def _read_firmware(self) -> None:
        """Read firmware version string from the gateway.

        The firmware string is typically ``MODEL_VERSION`` (e.g.
        ``GW2000A_V2.1.8``).  We split on ``_V`` to extract the model
        and version separately.
        """
        try:
            payload = await send_command(
                self._host, self._port, CMD_READ_FIRMWARE,
                timeout=self._timeout,
            )
            # First byte is string length, followed by ASCII bytes
            if len(payload) > 1:
                fw_len = payload[0]
                fw_str = payload[1:1 + fw_len].decode("ascii", errors="replace")
                self._firmware = fw_str.strip("\x00")

                # Extract model name (e.g. "GW2000A" from "GW2000A_V2.1.8")
                if "_V" in self._firmware:
                    self._model = self._firmware.split("_V")[0]
                else:
                    self._model = self._firmware
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("Failed to read Ecowitt firmware: %s", exc)

    async def _read_system_info(self) -> None:
        """Read system info (frequency, sensor type) from the gateway."""
        try:
            payload = await send_command(
                self._host, self._port, CMD_READ_SSSS,
                timeout=self._timeout,
            )
            if len(payload) >= 1:
                freq_map = {0: "433MHz", 1: "868MHz", 2: "915MHz", 3: "920MHz"}
                self._frequency = freq_map.get(payload[0], "unknown")
        except (ConnectionError, TimeoutError, OSError) as exc:
            logger.warning("Failed to read Ecowitt system info: %s", exc)

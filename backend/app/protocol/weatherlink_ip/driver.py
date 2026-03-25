"""Davis WeatherLink IP (6555) driver — Vantage protocol over TCP.

Thin wrapper around :class:`LinkDriver` with a :class:`TcpTransport`
injected as the transport layer.  All protocol operations (LOOP polling,
memory reads, archive sync, calibration, clock sync) are delegated to
the inner LinkDriver.
"""

import logging
from typing import Optional

from ..base import StationDriver, SensorSnapshot, HardwareInfo
from ..link_driver import LinkDriver
from .tcp_transport import TcpTransport, DEFAULT_PORT

logger = logging.getLogger(__name__)


class WeatherLinkIPDriver(StationDriver):
    """Davis WeatherLink IP (6555) driver.

    Creates a TCP transport and injects it into a standard LinkDriver.
    Exposes the StationDriver interface while giving logger_main.py access
    to the inner LinkDriver for hardware-specific operations.
    """

    def __init__(
        self,
        ip: str,
        port: int = DEFAULT_PORT,
        timeout: float = 4.0,
    ):
        self._ip = ip
        self._port = port
        transport = TcpTransport(host=ip, port=port, timeout=timeout)
        self._link = LinkDriver(transport=transport)

    # ---- StationDriver interface: delegate to inner LinkDriver ----

    async def connect(self) -> None:
        await self._link.connect()

    async def disconnect(self) -> None:
        await self._link.disconnect()

    async def poll(self) -> Optional[SensorSnapshot]:
        return await self._link.poll()

    async def detect_hardware(self) -> HardwareInfo:
        return await self._link.detect_hardware()

    @property
    def connected(self) -> bool:
        return self._link.connected

    @property
    def station_name(self) -> str:
        base = self._link.station_name
        return f"{base} (IP)" if base != "Unknown" else "WeatherLink IP"

    @property
    def capabilities(self) -> set[str]:
        return self._link.capabilities

    def request_stop(self) -> None:
        self._link.request_stop()

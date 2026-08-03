"""Davis WeatherLink IP (6555) driver — LEGACY WeatherLink protocol over TCP.

Thin wrapper around :class:`LinkDriver` with a :class:`TcpTransport`
injected as the transport layer.  All protocol operations (LOOP polling,
memory reads, archive sync, calibration, clock sync) are delegated to
the inner LinkDriver.

UNRESOLVED — see issue #247.  This docstring and the driver catalog entry
in ``app/api/station.py`` both used to say "Vantage protocol over TCP",
but the implementation wraps LinkDriver, which speaks the legacy
WRD/WWR/RRD/SRD command set — no ``BAR=``, no ``bardata()``, no LOOP2.
The header is corrected here to match what the code actually does, but
which of the two is *wrong* has not been settled: either the description
was always stale, or this should wrap VantageDriver and every
Vantage-only capability is silently missing.  Settling it needs a real
6555 on the bench.

Consequence for anyone adding a capability: do NOT infer this driver's
protocol from its name or its docs.  It inherits whatever LinkDriver
advertises.  This nearly put CAP_BAROMETER_CAL on a driver that cannot
execute ``BAR=``.
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

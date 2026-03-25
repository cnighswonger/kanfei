"""Driver abstraction layer for multi-vendor weather station support.

Defines the StationDriver ABC, SensorSnapshot canonical data class, and
HardwareInfo descriptor that all hardware drivers implement.  Consumers
(Poller, logger daemon, etc.) program against these abstractions so new
drivers can be added without modifying core infrastructure.

All sensor values in SensorSnapshot use **standard units** — the driver is
responsible for converting from its native format.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SensorSnapshot:
    """Canonical sensor data returned by every driver's poll() method.

    All values use SI units.  The driver is responsible for converting
    from its native format to SI before returning.  Everything downstream
    (poller, calculations, DB storage) assumes SI.
    """

    # Temperatures (°C)
    inside_temp: Optional[float] = None
    outside_temp: Optional[float] = None

    # Humidity (% 0-100)
    inside_humidity: Optional[int] = None
    outside_humidity: Optional[int] = None

    # Wind
    wind_speed: Optional[float] = None      # m/s
    wind_direction: Optional[int] = None    # degrees 0-359
    wind_gust: Optional[float] = None       # m/s

    # Barometer (hPa, sea-level corrected)
    barometer: Optional[float] = None

    # Rain
    rain_rate: Optional[float] = None       # mm/hr
    rain_daily: Optional[float] = None      # mm (since midnight)
    rain_yearly: Optional[float] = None     # mm (since Jan 1)

    # Solar / UV
    solar_radiation: Optional[int] = None   # W/m²
    uv_index: Optional[float] = None        # index

    # Soil / Leaf
    soil_temp: Optional[float] = None       # °C
    soil_moisture: Optional[int] = None     # centibars
    leaf_wetness: Optional[int] = None      # 0-15

    # Evapotranspiration (mm)
    et_daily: Optional[float] = None

    # Vendor-specific fields that don't map to the standard schema
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HardwareInfo:
    """Describes the detected hardware."""

    name: str               # Human-readable model name
    model_code: int          # Numeric station type identifier
    capabilities: set[str]   # Feature flags (see Capabilities below)


# --------------- Capability constants ---------------
# Drivers declare these so the UI and services can adapt.

CAP_ARCHIVE_SYNC = "archive_sync"        # Can retrieve historical records
CAP_CALIBRATION_RW = "calibration_rw"    # Can read/write calibration offsets
CAP_CLOCK_SYNC = "clock_sync"            # Can set station clock
CAP_RAIN_RESET = "rain_reset"            # Can clear rain accumulators
CAP_HILOWS = "hilows"                    # Can retrieve hi/low records


# --------------- Abstract base class ---------------

class StationDriver(ABC):
    """Interface that every hardware driver must implement."""

    @abstractmethod
    async def connect(self) -> None:
        """Open connection, detect hardware, perform initial setup."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Cleanly shut down the connection."""

    @abstractmethod
    async def poll(self) -> Optional[SensorSnapshot]:
        """Read current sensor values.

        Returns a SensorSnapshot in standard units, or None on failure.
        """

    @abstractmethod
    async def detect_hardware(self) -> HardwareInfo:
        """Identify the connected station model and capabilities."""

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the driver currently has an active connection."""

    @property
    @abstractmethod
    def station_name(self) -> str:
        """Human-readable name of the connected station model."""

    @property
    @abstractmethod
    def capabilities(self) -> set[str]:
        """Set of capability strings this driver supports."""

    def request_stop(self) -> None:
        """Signal the driver to abort any blocking I/O.

        Override if the driver uses blocking operations that need
        early termination (e.g. serial reads with long timeouts).
        """

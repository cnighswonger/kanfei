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

    # Evapotranspiration (mm).  Day/month/year are what the console reports
    # in LOOP1 — daily is a running total since local midnight, monthly and
    # yearly are running totals since their respective resets.  None on
    # stations that don't compute ET (needs solar + temp/humidity/wind).
    et_daily: Optional[float] = None
    et_monthly: Optional[float] = None
    et_yearly: Optional[float] = None

    # Station-computed THSW index (°C).  Every other derived value is
    # calculated from raw sensor readings in calculations.py; THSW needs
    # solar radiation, so only a station with a solar sensor can produce
    # one.  None on stations that lack the sensor, and on drivers that do
    # not report it at all.
    thsw_index: Optional[float] = None

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

# Settings-panel operations.  Declared separately from the coarse flags
# above because a driver can support one without the other: every Davis
# serial station has an archive period, but "sample period" is a
# WeatherLink-logger concept with no equivalent in the Vantage protocol.
#
# The settings handlers consult these rather than checking the driver's
# concrete type.  An isinstance(driver, LinkDriver) check is what made the
# whole settings panel dead on Vantage stations (#219) — and the same
# pattern caused #215 — so new config operations belong here, not in a
# type test.
CAP_ARCHIVE_PERIOD_RW = "archive_period_rw"   # Can read/write archive interval
CAP_SAMPLE_PERIOD_RW = "sample_period_rw"     # Can read/write sample period

# Barometer calibration via the Vantage BAR= primitive.
#
# Deliberately narrower than "this station can calibrate its barometer".
# Legacy WeatherLink stations (Monitor II, Wizard) CAN calibrate theirs,
# but by an incompatible mechanism: a direct BAR_CAL register write with
# SUBTRACT semantics (firmware computes Barometer = Barometer - BarCal,
# reference/techref.txt:1070; LinkDriver negates at the I/O boundary,
# #154).  A tool written for BAR= that ran against a legacy station would
# either fail outright or, worse, write an offset with the wrong sign and
# double the error rather than removing it.
#
# So this flag means specifically "speaks BAR=", not "is calibratable".
# Legacy needs its own capability and its own procedure; see the Vantage
# scope note in kanfei-phone-sensor's DAVIS-STATION-CALIBRATION.md.
#
# NOT on WeatherLink IP: despite the name, that driver wraps LinkDriver
# and speaks the legacy command set (#247).
CAP_BAROMETER_CAL = "barometer_cal"           # Can calibrate barometer via BAR=

# Station latitude/longitude held in console EEPROM.
#
# Distinct from Kanfei's own configured location: the console keeps its
# own copy and uses it for its sunrise/sunset calculation and pressure
# correction, so the two disagreeing produces quietly wrong derived data
# rather than an obvious failure.
#
# Vantage only.  The value is stored as signed tenths of a degree, which
# is ~11 km per step — coarser than anything Kanfei stores, so the two
# can never be compared for exact equality.
CAP_LOCATION_RW = "location_rw"               # Can read/write console lat/lon

# Yearly-rain-reset month.  Vantage only.  The console uses this to decide
# when the yearly rain accumulator drops back to zero — a west-coast US
# operator typically wants July (start of the hydrological "water year")
# so a mid-winter storm season is not split across two yearly totals.
# Legacy stations reset every January without exposing a knob.
CAP_RAIN_SEASON_RW = "rain_season_rw"          # Can read/write yearly-rain-reset month


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

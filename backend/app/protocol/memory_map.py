"""Station memory address constants per station type.

Each entry is (bank, address, n_nibbles).
Reference: techref.txt section IX (lines 1874+).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MemAddr:
    """A station memory address."""
    bank: int
    address: int
    nibbles: int


# ============================================================
# Monitor / Wizard / Perception - Bank 0
# ============================================================
class BasicBank0:
    MODEL = MemAddr(0, 0x4D, 1)
    WIND_SPEED = MemAddr(0, 0x5E, 2)
    WIND_SPEED_HI = MemAddr(0, 0x60, 4)
    WIND_SPEED_HI_TIME = MemAddr(0, 0x64, 4)
    WIND_SPEED_HI_DATE = MemAddr(0, 0x68, 3)
    WIND_SPEED_ALARM = MemAddr(0, 0x6B, 4)
    BAR_FLAGS = MemAddr(0, 0x79, 1)
    DEW_POINT = MemAddr(0, 0x8A, 4)
    DEW_POINT_HI = MemAddr(0, 0x8E, 4)
    DEW_POINT_LO = MemAddr(0, 0x92, 4)
    WIND_CHILL = MemAddr(0, 0xA8, 4)
    WIND_CHILL_LO = MemAddr(0, 0xAC, 4)


# ============================================================
# Monitor / Wizard / Perception - Bank 1
# ============================================================
class BasicBank1:
    BAROMETER = MemAddr(1, 0x00, 4)
    BAR_HI = MemAddr(1, 0x04, 4)
    BAR_LO = MemAddr(1, 0x08, 4)
    BAR_ALARM_HI = MemAddr(1, 0x18, 2)
    BAR_ALARM_LO = MemAddr(1, 0x1A, 2)
    BAR_CAL = MemAddr(1, 0x2C, 4)

    INSIDE_TEMP = MemAddr(1, 0x30, 4)
    INSIDE_TEMP_HI = MemAddr(1, 0x34, 4)
    INSIDE_TEMP_LO = MemAddr(1, 0x38, 4)
    INSIDE_TEMP_HI_TIME = MemAddr(1, 0x3C, 4)
    INSIDE_TEMP_LO_TIME = MemAddr(1, 0x40, 4)
    INSIDE_TEMP_ALARM_HI = MemAddr(1, 0x4A, 4)
    INSIDE_TEMP_ALARM_LO = MemAddr(1, 0x4E, 4)
    INSIDE_TEMP_CAL = MemAddr(1, 0x52, 4)

    OUTSIDE_TEMP = MemAddr(1, 0x56, 4)
    OUTSIDE_TEMP_HI = MemAddr(1, 0x5A, 4)
    OUTSIDE_TEMP_LO = MemAddr(1, 0x5E, 4)
    OUTSIDE_TEMP_HI_TIME = MemAddr(1, 0x62, 4)
    OUTSIDE_TEMP_LO_TIME = MemAddr(1, 0x66, 4)
    OUTSIDE_TEMP_ALARM_HI = MemAddr(1, 0x70, 4)
    OUTSIDE_TEMP_ALARM_LO = MemAddr(1, 0x74, 4)
    OUTSIDE_TEMP_CAL = MemAddr(1, 0x78, 4)

    INSIDE_HUMIDITY = MemAddr(1, 0x80, 2)
    INSIDE_HUMIDITY_HI = MemAddr(1, 0x82, 2)
    INSIDE_HUMIDITY_LO = MemAddr(1, 0x84, 2)

    OUTSIDE_HUMIDITY = MemAddr(1, 0x98, 2)
    OUTSIDE_HUMIDITY_HI = MemAddr(1, 0x9A, 2)
    OUTSIDE_HUMIDITY_LO = MemAddr(1, 0x9C, 2)
    OUTSIDE_HUMIDITY_CAL = MemAddr(1, 0xDA, 4)

    WIND_DIRECTION = MemAddr(1, 0xB4, 4)

    TIME = MemAddr(1, 0xBE, 6)
    TIME_ALARM = MemAddr(1, 0xC4, 4)
    DATE = MemAddr(1, 0xC8, 5)

    RAIN_YEARLY = MemAddr(1, 0xCE, 4)
    RAIN_DAILY = MemAddr(1, 0xD2, 4)
    RAIN_CAL = MemAddr(1, 0xD6, 4)


# ============================================================
# Link processor memory (Bank 1) - Sensor image locations
# ============================================================
class LinkBank1:
    """Link processor memory addresses for sensor image (RRD command)."""
    NEW_ARCHIVE_PTR = MemAddr(1, 0x00, 4)
    OLD_ARCHIVE_PTR = MemAddr(1, 0x04, 4)
    INSIDE_TEMP = MemAddr(1, 0x1C, 4)
    OUTSIDE_TEMP = MemAddr(1, 0x20, 4)
    WIND_SPEED = MemAddr(1, 0x24, 2)
    WIND_DIRECTION = MemAddr(1, 0x26, 4)
    BAROMETER = MemAddr(1, 0x2A, 4)
    INSIDE_HUMIDITY = MemAddr(1, 0x2E, 2)
    OUTSIDE_HUMIDITY = MemAddr(1, 0x30, 2)
    RAIN = MemAddr(1, 0x32, 4)
    SAMPLE_PERIOD = MemAddr(0, 0x13A, 2)
    ARCHIVE_PERIOD = MemAddr(0, 0x13C, 2)


# ============================================================
# Link processor memory (Bank 1) - GroWeather/Energy/Health
# ============================================================
class GroWeatherLinkBank1:
    """Link processor memory addresses for GroWeather/Energy/Health (RRD command).

    Archive pointers are at different offsets than basic stations.
    """
    OLD_ARCHIVE_PTR = MemAddr(1, 0x06, 4)
    NEW_ARCHIVE_PTR = MemAddr(1, 0x0A, 4)
    ARCHIVE_PERIOD = MemAddr(0, 0x152, 2)


# ============================================================
# GroWeather - Bank 0
# ============================================================
class GroWeatherBank0:
    MODEL = MemAddr(0, 0x4D, 1)
    WIND_SPEED = MemAddr(0, 0x60, 2)
    WIND_SPEED_HI = MemAddr(0, 0x62, 2)
    WIND_SPEED_HI_TIME = MemAddr(0, 0x64, 4)
    WIND_SPEED_ALARM = MemAddr(0, 0x68, 2)
    WIND_SPEED_CAL = MemAddr(0, 0x6A, 4)
    BAR_FLAGS = MemAddr(0, 0x7A, 1)
    POWER_FLAGS = MemAddr(0, 0x7B, 1)
    DEW_POINT = MemAddr(0, 0x8A, 3)
    WIND_CHILL = MemAddr(0, 0x8E, 3)
    WIND_CHILL_LO = MemAddr(0, 0x91, 3)
    WIND_RUN_DAILY = MemAddr(0, 0x9E, 4)
    WIND_RUN_TOTAL = MemAddr(0, 0xA2, 5)
    ET_DAILY = MemAddr(0, 0xA7, 3)
    ET_TOTAL = MemAddr(0, 0xAD, 4)


# ============================================================
# GroWeather - Bank 1
# ============================================================
class GroWeatherBank1:
    BAROMETER = MemAddr(1, 0x00, 4)
    BAR_CAL = MemAddr(1, 0x20, 4)
    SOIL_TEMP = MemAddr(1, 0x30, 3)
    SOIL_TEMP_CAL = MemAddr(1, 0x3F, 3)
    AIR_TEMP = MemAddr(1, 0x42, 3)
    AIR_TEMP_CAL = MemAddr(1, 0x51, 3)
    OUTSIDE_HUMIDITY = MemAddr(1, 0x73, 2)
    OUTSIDE_HUMIDITY_CAL = MemAddr(1, 0x85, 2)
    WIND_DIRECTION = MemAddr(1, 0x8B, 3)
    TIME = MemAddr(1, 0x94, 6)
    DATE = MemAddr(1, 0x9E, 5)
    SOLAR_RAD = MemAddr(1, 0xB8, 3)
    RAIN_YEARLY = MemAddr(1, 0xC5, 4)
    RAIN_DAILY = MemAddr(1, 0xC9, 3)
    RAIN_CAL = MemAddr(1, 0xCF, 4)
    RAIN_RATE = MemAddr(1, 0xD3, 3)
    LEAF_WETNESS = MemAddr(1, 0xDE, 1)

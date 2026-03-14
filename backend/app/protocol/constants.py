"""Protocol constants for the Davis WeatherLink serial interface."""

from enum import IntEnum

# Response codes
ACK = 0x06  # Command accepted
NAK = 0x15  # Command not understood (serial.h)
NOT_UNDERSTOOD = 0x21  # Command not understood (techref.txt)
CAN = 0x18  # CRC checksum failed (Rev E only)
ESC = 0x1B  # Escape
SOH = 0x01  # Start of LOOP block header

# Serial defaults (2400 is the WeatherLink factory default)
DEFAULT_BAUD = 2400
DATA_BITS = 8
STOP_BITS = 1
PARITY = "N"

# Retry
MAX_RETRIES = 2

# Command terminator
CR = 0x0D


class StationModel(IntEnum):
    """Station model codes from appendix.txt address 0x004D."""
    WIZARD_III = 0
    WIZARD_II = 1
    MONITOR = 2
    PERCEPTION = 3
    GROWEATHER = 4
    ENERGY = 5
    HEALTH = 6
    OLD_LINK = 0xF


# Station model display names
STATION_NAMES = {
    StationModel.WIZARD_III: "Weather Wizard III",
    StationModel.WIZARD_II: "Weather Wizard II",
    StationModel.MONITOR: "Weather Monitor II",
    StationModel.PERCEPTION: "Perception II",
    StationModel.GROWEATHER: "GroWeather",
    StationModel.ENERGY: "Energy",
    StationModel.HEALTH: "Health",
    StationModel.OLD_LINK: "Old Link (Monitor/Wizard)",
}

# Stations that share the Monitor/Wizard/Perception LOOP format (15 bytes)
BASIC_STATIONS = {
    StationModel.WIZARD_III,
    StationModel.WIZARD_II,
    StationModel.MONITOR,
    StationModel.PERCEPTION,
    StationModel.OLD_LINK,
}

# LOOP data sizes per station type (data bytes, excluding SOH and CRC)
LOOP_DATA_SIZE = {
    StationModel.WIZARD_III: 15,
    StationModel.WIZARD_II: 15,
    StationModel.MONITOR: 15,
    StationModel.PERCEPTION: 15,
    StationModel.OLD_LINK: 15,
    StationModel.GROWEATHER: 33,
    StationModel.ENERGY: 27,
    StationModel.HEALTH: 25,
}

# Invalid data markers
INVALID_TEMP_4NIB = 0x7FFF  # or 0x8000 for "not connected"
INVALID_TEMP_NOT_CONNECTED = 0x8000
INVALID_TEMP_3NIB = 0x7FF
INVALID_HUMIDITY = 0x80  # 128
INVALID_WIND_DIR = 0xFF  # archived direction
INVALID_WIND_DIR_4NIB = 0x7FFF
INVALID_SOLAR_RAD = 0xFFF  # 4095
INVALID_UV = 0xFF  # 255

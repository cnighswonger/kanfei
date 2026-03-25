"""Protocol constants for the Davis Vantage serial interface.

Covers Vantage Pro1, Pro2, and Vue stations.  The Vantage protocol is
fundamentally different from the legacy WeatherLink protocol used by
Weather Monitor II / Wizard / GroWeather.
"""

from enum import IntEnum

# --------------- Serial defaults ---------------

VANTAGE_DEFAULT_BAUD = 19200  # factory default (configurable 1200–19200)

# --------------- Wakeup ---------------

WAKEUP = b"\n"
WAKEUP_RESPONSE = b"\n\r"
WAKEUP_TIMEOUT = 1.2   # seconds between retries
WAKEUP_MAX_RETRIES = 3

# --------------- Response codes ---------------

ACK = 0x06
NAK = 0x21   # command not understood / CRC error
CAN = 0x18   # cancel (legacy compat)
ESC = 0x1B   # escape / abort (used to cancel DMPAFT)

# --------------- Packet sizes ---------------

LOOP_PACKET_SIZE = 99    # bytes including "LOO" header + data + \n\r + CRC
LOOP2_PACKET_SIZE = 99

LOOP_HEADER = b"LOO"

# --------------- Archive ---------------

ARCHIVE_PAGE_SIZE = 267          # 5 × 52 records + 4 unused + 2 CRC
ARCHIVE_RECORD_SIZE = 52
ARCHIVE_RECORDS_PER_PAGE = 5

# --------------- Retry ---------------

MAX_RETRIES = 3

# --------------- Station model codes ---------------
# EEPROM offset 0x12


class VantageModel(IntEnum):
    """Station type codes from EEPROM offset 0x12."""
    VANTAGE_PRO = 16   # VP1 and VP2 both report 16
    VANTAGE_VUE = 17


VANTAGE_NAMES = {
    VantageModel.VANTAGE_PRO: "Vantage Pro2",
    VantageModel.VANTAGE_VUE: "Vantage Vue",
}

# --------------- Rain collector types ---------------
# EEPROM 0x2B (setup bits) bits 4-5

RAIN_COLLECTOR_01_IN = 0     # 0.01″ per click (standard US)
RAIN_COLLECTOR_02_MM = 1     # 0.2 mm per click
RAIN_COLLECTOR_01_MM = 2     # 0.1 mm per click

RAIN_CLICK_INCHES = {
    RAIN_COLLECTOR_01_IN: 0.01,
    RAIN_COLLECTOR_02_MM: 0.2 * 0.03937007874,   # 0.00787″
    RAIN_COLLECTOR_01_MM: 0.1 * 0.03937007874,   # 0.003937″
}

# --------------- Invalid data sentinels ---------------

INVALID_TEMP = 0x7FFF       # 32767 — signed temp fields
INVALID_HUMIDITY = 0xFF     # 255
INVALID_UV = 0xFF           # 255
INVALID_SOLAR = 0x7FFF      # 32767
INVALID_BAROMETER = 0       # 0 means no reading
INVALID_RAIN_RATE = 0xFFFF  # 65535
INVALID_WIND_DIR = 0x7FFF   # 32767 (or 0 = calm)
INVALID_EXTRA_TEMP = 0xFF   # 255 (offset-encoded temps)

# --------------- Bar trend codes ---------------

BAR_TREND_FALLING_RAPIDLY = -60
BAR_TREND_FALLING_SLOWLY = -20
BAR_TREND_STEADY = 0
BAR_TREND_RISING_SLOWLY = 20
BAR_TREND_RISING_RAPIDLY = 60
BAR_TREND_UNKNOWN = 0x50    # 80 — revision A / not available

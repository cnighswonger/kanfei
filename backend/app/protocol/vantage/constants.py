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

ARCHIVE_PAGE_SIZE = 267          # 1 seq + 5 × 52 records + 4 unused + 2 CRC
ARCHIVE_PAGE_HEADER_SIZE = 1     # leading sequence byte, before record 0
ARCHIVE_RECORD_SIZE = 52
ARCHIVE_RECORDS_PER_PAGE = 5

# DMPAFT response header: page_count (u16 LE) + first_record_offset (u16 LE)
# + CRC (u16 BE).  The station waits for an ACK after this before sending
# page 0.
DMPAFT_HEADER_SIZE = 6

# --------------- Calibration ---------------

# CALED / CALFIX exchange a 43-byte block (section X.6):
#   inside temp      0   2      leaf temps      26  8  (4 x 2)
#   outside temp     2   2      inside hum      34  1
#   extra temps      4  14      outside hum     35  1
#   soil temps      18   8      extra hums      36  7
CALFIX_BLOCK_SIZE = 43
CALFIX_OFF_INSIDE_TEMP = 0
CALFIX_OFF_OUTSIDE_TEMP = 2
CALFIX_OFF_INSIDE_HUM = 34
CALFIX_OFF_OUTSIDE_HUM = 35

# Sentinels meaning "no sensor / dashed" in a CALED block.  Per XIV.1 these
# must be left alone rather than back-calculated, or garbage is written
# into the console's display values.
CALFIX_INVALID_TEMP = 0x7FFF
CALFIX_INVALID_HUM = 0xFF

# The EEPROM calibration block really spans 0x32..0x4E (29 bytes).
#
# Do NOT use the manual's own "EEBRD 32 2B" / "EEBWR 32 2B" example from
# section XIV.1: 0x2B is 43, the size of the CALFIX *data block*, not of
# the EEPROM region.  A 43-byte write at 0x32 runs to 0x5C, past the end
# of the calibration block and over DEFAULT_BAR_GRAPH (0x4F),
# DEFAULT_RAIN_GRAPH (0x50), DEFAULT_SPEED_GRAPH (0x51) and 11 bytes of
# ALARM_START (0x52).  The manual's own prose two lines earlier says
# "28 EEPROM bytes", and its address map implies 29 — the three do not
# agree, so this driver writes individual fields instead.
CAL_BLOCK_START = 0x32
CAL_BLOCK_END = 0x4E

# --------------- Retry ---------------

MAX_RETRIES = 3

# --------------- Station model codes ---------------
# Read from station PROCESSOR MEMORY at address 0x4D via the WRD command
# -- NOT from EEPROM.  These are different address spaces; EEBRD 0x12
# returns 0x00 on a Vue, which is what previously made every Vue report
# itself as a Pro2.
STATION_TYPE_WRD_ADDR = 0x4D


class VantageModel(IntEnum):
    """Station type codes from processor memory 0x4D (WRD)."""
    UNKNOWN = -1       # detection failed or unrecognised code
    VANTAGE_PRO = 16   # VP1 and VP2 both report 16
    VANTAGE_VUE = 17


VANTAGE_NAMES = {
    VantageModel.UNKNOWN: "Vantage (unknown model)",
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

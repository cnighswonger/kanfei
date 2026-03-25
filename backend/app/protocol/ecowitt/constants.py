"""Ecowitt LAN API protocol constants.

Defines command bytes, sensor marker bytes and their data sizes, and
protocol defaults.  Marker table sourced from weewx-gw1000 driver.
"""

# ---- Protocol defaults ----

DEFAULT_PORT = 45000
DEFAULT_TIMEOUT = 5.0
MAX_RETRIES = 2
HEADER = b"\xff\xff"

# ---- Command bytes ----

CMD_READ_FIRMWARE = 0x50
CMD_READ_SSSS = 0x30          # System info (frequency, sensor type, UTC)
CMD_READ_STATION_MAC = 0x26
CMD_LIVEDATA = 0x27
CMD_READ_RAIN = 0x57          # Extended rain data
CMD_READ_SENSOR_ID = 0x3A
CMD_READ_SENSOR_ID_NEW = 0x3C

# Commands whose responses use a 2-byte size field (all others use 1-byte).
LONG_SIZE_COMMANDS: frozenset[int] = frozenset({
    CMD_LIVEDATA,
    CMD_READ_RAIN,
    CMD_READ_SENSOR_ID_NEW,
})

# ---- Sensor marker bytes ----
# Mapping of every known marker to its data-byte count.  The parser
# cannot skip unknown markers (no length prefix), so this table must
# be comprehensive.  Values sourced from weewx-gw1000 driver.

MARKER_SIZE: dict[int, int] = {
    # Core weather
    0x01: 2,   # indoor temp          (signed i16 /10, °C)
    0x02: 2,   # outdoor temp         (signed i16 /10, °C)
    0x03: 2,   # dew point            (signed i16 /10, °C)
    0x04: 2,   # wind chill           (signed i16 /10, °C)
    0x05: 2,   # heat index           (signed i16 /10, °C)
    0x06: 1,   # indoor humidity      (u8, %)
    0x07: 1,   # outdoor humidity     (u8, %)
    0x08: 2,   # abs barometer        (u16 /10, hPa)
    0x09: 2,   # rel barometer        (u16 /10, hPa)
    0x0A: 2,   # wind direction       (u16, degrees)
    0x0B: 2,   # wind speed           (u16 /10, m/s)
    0x0C: 2,   # gust speed           (u16 /10, m/s)

    # Rain (2-byte, traditional)
    0x0D: 2,   # rain event           (u16 /10, mm)
    0x0E: 2,   # rain rate            (u16 /10, mm/hr)
    0x0F: 2,   # rain gain            (u16 /100)
    0x10: 2,   # rain day             (u16 /10, mm)  -- 4 bytes in CMD_READ_RAIN!
    0x11: 2,   # rain week            (u16 /10, mm)  -- 4 bytes in CMD_READ_RAIN!

    # Rain (4-byte, large accumulators)
    0x12: 4,   # rain month           (u32 /10, mm)
    0x13: 4,   # rain year            (u32 /10, mm)
    0x14: 4,   # rain totals          (u32 /10, mm)

    # Solar / UV
    0x15: 4,   # light                (u32 /10, lux)
    0x16: 2,   # solar radiation      (u16 /10, W/m²)
    0x17: 1,   # UV index             (u8, index 0-15)

    # DateTime + max daily wind
    0x18: 6,   # datetime             (YY MM DD HH MM SS)
    0x19: 2,   # max daily wind       (u16 /10, m/s)

    # Multi-channel temp ch1-8
    0x1A: 2,   # temp ch1             (signed i16 /10, °C)
    0x1B: 2,   # temp ch2
    0x1C: 2,   # temp ch3
    0x1D: 2,   # temp ch4
    0x1E: 2,   # temp ch5
    0x1F: 2,   # temp ch6
    0x20: 2,   # temp ch7
    0x21: 2,   # temp ch8

    # Multi-channel humidity ch1-8
    0x22: 1,   # humidity ch1         (u8, %)
    0x23: 1,   # humidity ch2
    0x24: 1,   # humidity ch3
    0x25: 1,   # humidity ch4
    0x26: 1,   # humidity ch5
    0x27: 1,   # humidity ch6
    0x28: 1,   # humidity ch7
    0x29: 1,   # humidity ch8

    # PM2.5 ch1
    0x2A: 2,   # PM2.5 ch1            (u16 /10, µg/m³)

    # Soil sensors (interleaved temp + moisture, ch1-16)
    0x2B: 2,   # soil temp ch1        (signed i16 /10, °C)
    0x2C: 1,   # soil moisture ch1    (u8, %)
    0x2D: 2,   # soil temp ch2
    0x2E: 1,   # soil moisture ch2
    0x2F: 2,   # soil temp ch3
    0x30: 1,   # soil moisture ch3
    0x31: 2,   # soil temp ch4
    0x32: 1,   # soil moisture ch4
    0x33: 2,   # soil temp ch5
    0x34: 1,   # soil moisture ch5
    0x35: 2,   # soil temp ch6
    0x36: 1,   # soil moisture ch6
    0x37: 2,   # soil temp ch7
    0x38: 1,   # soil moisture ch7
    0x39: 2,   # soil temp ch8
    0x3A: 1,   # soil moisture ch8
    0x3B: 2,   # soil temp ch9
    0x3C: 1,   # soil moisture ch9
    0x3D: 2,   # soil temp ch10
    0x3E: 1,   # soil moisture ch10
    0x3F: 2,   # soil temp ch11
    0x40: 1,   # soil moisture ch11
    0x41: 2,   # soil temp ch12
    0x42: 1,   # soil moisture ch12
    0x43: 2,   # soil temp ch13
    0x44: 1,   # soil moisture ch13
    0x45: 2,   # soil temp ch14
    0x46: 1,   # soil moisture ch14
    0x47: 2,   # soil temp ch15
    0x48: 1,   # soil moisture ch15
    0x49: 2,   # soil temp ch16
    0x4A: 1,   # soil moisture ch16

    # Battery status (legacy, firmware <= 1.6.4)
    0x4C: 16,  # low battery flags

    # PM2.5 24h averages
    0x4D: 2,   # PM2.5 ch1 24h avg    (u16 /10, µg/m³)
    0x4E: 2,   # PM2.5 ch2 24h avg
    0x4F: 2,   # PM2.5 ch3 24h avg
    0x50: 2,   # PM2.5 ch4 24h avg

    # PM2.5 additional channels
    0x51: 2,   # PM2.5 ch2            (u16 /10, µg/m³)
    0x52: 2,   # PM2.5 ch3
    0x53: 2,   # PM2.5 ch4

    # Leak detection ch1-4
    0x58: 1,   # leak ch1             (u8, 0=no leak, 1=leak)
    0x59: 1,   # leak ch2
    0x5A: 1,   # leak ch3
    0x5B: 1,   # leak ch4

    # Lightning
    0x60: 1,   # lightning distance   (u8, km, 0-40)
    0x61: 4,   # lightning det. time  (u32, epoch seconds)
    0x62: 4,   # lightning count      (u32)

    # WN34 temp sensors ch1-8 (temp + battery)
    0x63: 3,   # temp ch9             (i16 /10 + u8 battery)
    0x64: 3,   # temp ch10
    0x65: 3,   # temp ch11
    0x66: 3,   # temp ch12
    0x67: 3,   # temp ch13
    0x68: 3,   # temp ch14
    0x69: 3,   # temp ch15
    0x6A: 3,   # temp ch16

    # WH46 air quality (compound)
    0x6B: 24,  # pm10/pm25/co2/pm1/pm4 + temps + 24h avgs

    # Heap free memory
    0x6C: 4,   # free heap            (u32, bytes)

    # WH45 air quality (compound)
    0x70: 16,  # temp/humi/pm10/pm25/co2 + 24h avgs

    # Leaf wetness ch1-8
    0x72: 1,   # leaf wetness ch1     (u8, 0-100)
    0x73: 1,   # leaf wetness ch2
    0x74: 1,   # leaf wetness ch3
    0x75: 1,   # leaf wetness ch4
    0x76: 1,   # leaf wetness ch5
    0x77: 1,   # leaf wetness ch6
    0x78: 1,   # leaf wetness ch7
    0x79: 1,   # leaf wetness ch8
}

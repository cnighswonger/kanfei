"""Constants for the WeatherLink Live local HTTP API driver.

Defines data structure type IDs, rain click conversion factors,
network defaults, and staleness thresholds.
"""

# --------------- Network defaults ---------------

DEFAULT_HTTP_PORT = 80
API_PATH = "/v1/current_conditions"
HTTP_TIMEOUT_SECS = 10.0

# --------------- Staleness thresholds ---------------
# WLL updates its internal sensors approximately every 10 seconds.

STALE_WARNING_SECS = 60       # Log warning if no successful poll for 1 minute
STALE_DISCONNECT_SECS = 180   # Mark disconnected if no data for 3 minutes

# --------------- WLL data structure types ---------------

DATA_TYPE_ISS = 1            # ISS (Integrated Sensor Suite)
DATA_TYPE_LEAF_SOIL = 2      # Leaf/Soil moisture station
DATA_TYPE_BAROMETER = 3      # Barometric pressure (LSS BAR)
DATA_TYPE_INDOOR = 4         # Indoor temp/humidity (LSS)

# --------------- Rain click sizes ---------------
# The rain_size field in ISS data indicates the tipping bucket size.
# Convert raw click counts to inches by multiplying by the size.

RAIN_CLICK_INCHES: dict[int, float] = {
    1: 0.01,           # 0.01 inches per click (standard US)
    2: 0.2 / 25.4,     # 0.2 mm per click → inches
    3: 0.1 / 25.4,     # 0.1 mm per click → inches
}
DEFAULT_RAIN_CLICK_INCHES = 0.01

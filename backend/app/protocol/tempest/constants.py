"""WeatherFlow Tempest protocol constants.

UDP broadcast on port 50222, JSON-encoded datagrams.
Reference: https://weatherflow.github.io/Tempest/api/udp/v171/
"""

# --------------- Network ---------------

UDP_PORT = 50222
UDP_BIND = "0.0.0.0"
SCAN_TIMEOUT = 15.0          # seconds to wait for hub during probe/scan

# --------------- Message types ---------------

MSG_OBS_ST = "obs_st"             # Tempest all-in-one observation (60s)
MSG_OBS_AIR = "obs_air"           # Legacy Air sensor observation (60s)
MSG_OBS_SKY = "obs_sky"           # Legacy Sky sensor observation (60s)
MSG_RAPID_WIND = "rapid_wind"     # High-frequency wind (3s)
MSG_HUB_STATUS = "hub_status"     # Hub health (12s)
MSG_DEVICE_STATUS = "device_status"  # Per-device health (12s)
MSG_EVT_PRECIP = "evt_precip"     # Rain onset event
MSG_EVT_STRIKE = "evt_strike"     # Lightning strike event

OBSERVATION_TYPES = frozenset({MSG_OBS_ST, MSG_OBS_AIR, MSG_OBS_SKY})

# --------------- obs_st field indices (18 fields) ---------------

ST_TIMESTAMP = 0
ST_WIND_LULL = 1
ST_WIND_AVG = 2
ST_WIND_GUST = 3
ST_WIND_DIR = 4
ST_WIND_SAMPLE_INTERVAL = 5
ST_PRESSURE = 6
ST_TEMP = 7
ST_HUMIDITY = 8
ST_ILLUMINANCE = 9
ST_UV_INDEX = 10
ST_SOLAR_RAD = 11
ST_RAIN_ACCUM = 12
ST_PRECIP_TYPE = 13
ST_LIGHTNING_DIST = 14
ST_LIGHTNING_COUNT = 15
ST_BATTERY = 16
ST_REPORT_INTERVAL = 17
ST_FIELD_COUNT = 18

# --------------- obs_air field indices (8 fields) ---------------

AIR_TIMESTAMP = 0
AIR_PRESSURE = 1
AIR_TEMP = 2
AIR_HUMIDITY = 3
AIR_LIGHTNING_COUNT = 4
AIR_LIGHTNING_DIST = 5
AIR_BATTERY = 6
AIR_REPORT_INTERVAL = 7
AIR_FIELD_COUNT = 8

# --------------- obs_sky field indices (14 fields) ---------------

SKY_TIMESTAMP = 0
SKY_ILLUMINANCE = 1
SKY_UV_INDEX = 2
SKY_RAIN_ACCUM = 3
SKY_WIND_LULL = 4
SKY_WIND_AVG = 5
SKY_WIND_GUST = 6
SKY_WIND_DIR = 7
SKY_BATTERY = 8
SKY_REPORT_INTERVAL = 9
SKY_SOLAR_RAD = 10
SKY_DAILY_RAIN = 11          # Always null in UDP API
SKY_PRECIP_TYPE = 12
SKY_WIND_SAMPLE_INTERVAL = 13
SKY_FIELD_COUNT = 14

# --------------- rapid_wind field indices (3 fields) ---------------
# Note: rapid_wind uses "ob" key (single array), not "obs" (array of arrays)

RW_TIMESTAMP = 0
RW_WIND_SPEED = 1
RW_WIND_DIR = 2
RW_FIELD_COUNT = 3

# --------------- evt_strike field indices (3 fields) ---------------

STRIKE_TIMESTAMP = 0
STRIKE_DISTANCE = 1
STRIKE_ENERGY = 2

# --------------- Precipitation types ---------------

PRECIP_NONE = 0
PRECIP_RAIN = 1
PRECIP_HAIL = 2
PRECIP_MIX = 3

# --------------- Staleness thresholds ---------------

STALE_WARNING_SECS = 120     # Log warning if no obs for this long
STALE_DISCONNECT_SECS = 300  # Mark as disconnected if no obs for this long

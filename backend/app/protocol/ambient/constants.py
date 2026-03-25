"""Constants for the Ambient Weather / Fine Offset HTTP push protocol.

Defines field name mappings for both Wunderground and Ecowitt push formats,
default port/bind settings, and staleness thresholds.
"""

# --------------- Network defaults ---------------

DEFAULT_HTTP_PORT = 8080
HTTP_BIND = "0.0.0.0"

# --------------- Staleness thresholds ---------------

STALE_WARNING_SECS = 120     # Log warning if no data for 2 minutes
STALE_DISCONNECT_SECS = 300  # Mark disconnected if no data for 5 minutes

# --------------- Setup scan timeout ---------------

SCAN_TIMEOUT = 90.0  # Stations push every ~60s, wait 90s

# --------------- Format detection ---------------

ECOWITT_INDICATORS = frozenset({"PASSKEY", "stationtype", "model"})
WU_INDICATORS = frozenset({"ID", "PASSWORD", "action"})

# --------------- Field mapping tables ---------------
#
# Each entry: param_name -> (snapshot_field, is_extra, type)
#   snapshot_field: attribute name on SensorSnapshot (or key in extra dict)
#   is_extra: True if the value goes into extra dict, False if it's a direct field
#   type: callable for type coercion (float, int)

WU_FIELD_MAP: dict[str, tuple[str, bool, type]] = {
    # Primary weather fields
    "tempf":            ("outside_temp",      False, float),
    "humidity":         ("outside_humidity",   False, int),
    "baromin":          ("barometer",          False, float),
    "windspeedmph":     ("wind_speed",         False, int),
    "winddir":          ("wind_direction",     False, int),
    "windgustmph":      ("wind_gust",          False, int),
    "rainin":           ("rain_rate",          False, float),
    "dailyrainin":      ("rain_daily",         False, float),
    "yearlyrainin":     ("rain_yearly",        False, float),
    "solarradiation":   ("solar_radiation",    False, int),
    "UV":               ("uv_index",           False, float),
    # Indoor
    "indoortempf":      ("inside_temp",        False, float),
    "indoorhumidity":   ("inside_humidity",    False, int),
    # Soil / leaf
    "soiltempf":        ("soil_temp",          False, float),
    "soilmoisture":     ("soil_moisture",      False, int),
    "leafwetness":      ("leaf_wetness",       False, int),
    # Extra / derived
    "dewptf":           ("dew_point_f",        True,  float),
    "windchillf":       ("wind_chill_f",       True,  float),
    "hourlyrainin":     ("rain_hourly",        True,  float),
    "weeklyrainin":     ("rain_weekly",        True,  float),
    "monthlyrainin":    ("rain_monthly",       True,  float),
}

ECOWITT_FIELD_MAP: dict[str, tuple[str, bool, type]] = {
    # Primary weather fields (many share WU names)
    "tempf":            ("outside_temp",          False, float),
    "humidity":         ("outside_humidity",       False, int),
    "baromrelin":       ("barometer",              False, float),
    "windspeedmph":     ("wind_speed",             False, int),
    "winddir":          ("wind_direction",         False, int),
    "windgustmph":      ("wind_gust",              False, int),
    "rainratein":       ("rain_rate",              False, float),
    "dailyrainin":      ("rain_daily",             False, float),
    "yearlyrainin":     ("rain_yearly",            False, float),
    "solarradiation":   ("solar_radiation",        False, int),
    "uv":               ("uv_index",               False, float),
    # Indoor
    "tempinf":          ("inside_temp",            False, float),
    "humidityin":       ("inside_humidity",        False, int),
    # Absolute pressure
    "baromabsin":       ("station_pressure_inhg",  True,  float),
    # Extended rain
    "eventrainin":      ("rain_event",             True,  float),
    "hourlyrainin":     ("rain_hourly",            True,  float),
    "weeklyrainin":     ("rain_weekly",            True,  float),
    "monthlyrainin":    ("rain_monthly",           True,  float),
    # Gust
    "maxdailygust":     ("max_daily_gust",         True,  float),
    # Soil CH1 (primary)
    "soilmoisture1":    ("soil_moisture",          False, int),
    # Lightning
    "lightning_num":    ("lightning_count",         True,  int),
    "lightning":        ("lightning_distance_km",   True,  float),
}

# Multi-channel Ecowitt extras — these are handled programmatically
# in sensors.py by regex matching (soilmoisture2-8, tf_ch1-8, etc.)
ECOWITT_MULTI_CHANNEL_PATTERNS: dict[str, tuple[str, type]] = {
    "soilmoisture":     ("soil_moisture_ch",   int),
    "tf_ch":            ("temp_ch",            float),
    "leafwetness_ch":   ("leaf_wetness_ch",    int),
    "pm25_ch":          ("pm25_ch",            float),
    "pm25batt":         ("pm25_batt_ch",       int),
    "soilad":           ("soil_ad_ch",         int),
    "tf_batt":          ("temp_batt_ch",       int),
    "leak_ch":          ("leak_ch",            int),
}

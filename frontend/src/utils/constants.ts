// ============================================================
// Application-wide constants for the Davis Weather Station UI.
// ============================================================

/** Base URL for REST API calls (empty string = same origin). */
export const API_BASE = "";

/** Initial WebSocket reconnect delay in milliseconds. */
export const WS_RECONNECT_INTERVAL = 1000;

/** Maximum WebSocket reconnect delay in milliseconds. */
export const WS_MAX_RECONNECT_INTERVAL = 30000;

/** REST polling interval for current conditions fallback (ms). */
export const POLL_INTERVAL = 5000;

/** How often to refresh astronomy / station-status data (ms). */
export const ASTRONOMY_REFRESH_INTERVAL = 300_000; // 5 minutes

/** How often to auto-refresh forecast data (ms). */
export const FORECAST_REFRESH_INTERVAL = 1_800_000; // 30 minutes

/** Interval between WebSocket keep-alive pings (ms). */
export const WS_PING_INTERVAL = 30_000;

// --- Display names for sensor keys ---

export const SENSOR_DISPLAY_NAMES: Record<string, string> = {
  temperature_inside: "Indoor Temperature",
  temperature_outside: "Outdoor Temperature",
  humidity_inside: "Indoor Humidity",
  humidity_outside: "Outdoor Humidity",
  wind_speed: "Wind Speed",
  wind_direction: "Wind Direction",
  barometer: "Barometer",
  rain_daily: "Daily Rain",
  rain_yearly: "Yearly Rain",
  rain_rate: "Rain Rate",
  solar_radiation: "Solar Radiation",
  uv_index: "UV Index",
  heat_index: "Heat Index",
  dew_point: "Dew Point",
  wind_chill: "Wind Chill",
  feels_like: "Feels Like",
};

// --- Unit labels ---

export const UNIT_LABELS: Record<string, string> = {
  F: "\u00B0F",
  C: "\u00B0C",
  inHg: " inHg",
  hPa: " hPa",
  mph: " mph",
  kph: " km/h",
  knots: " kn",
  in: " in",
  mm: " mm",
  deg: "\u00B0",
  "%": "%",
  "W/m²": " W/m\u00B2",
};

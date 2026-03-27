/**
 * Expected display values for the anchor reading (row 120 in test.db).
 * These values are the single source of truth — both build-test-db.py
 * and the spec files reference these exact strings.
 *
 * Conversion chain: raw SI integer → backend convert() → API JSON → frontend render
 */

export const ANCHOR = {
  // Temperature gauges: value.toFixed(1)°unit
  outsideTemp: '75.2',
  insideTemp: '70.0',

  // Humidity gauges: ${value}%
  outsideHumidity: '62',
  insideHumidity: '45',

  // Wind compass: speed.toFixed(0) + unit, cardinal + direction°
  windSpeed: '8',
  windUnit: 'mph',
  windCardinal: 'SW',
  windDirection: '225',

  // Barometer: value.toFixed(2) + unit
  barometer: '30.02',
  barometerUnit: 'inHg',

  // Rain: value.toFixed(2)
  rainRate: '0.00',
  rainDaily: '0.00',
  rainYearly: '1.00',
  rainYesterday: '0.12',
  rainUnit: 'in',

  // Derived conditions: value.toFixed(1) + ' ' + unit
  feelsLike: '77.0 F',
  heatIndex: '77.0 F',
  dewPoint: '62.6 F',
  windChill: '75.2 F',
  thetaE: '330.0 K',

  // Pressure trend
  pressureTrend: 'rising',
  trendArrowUp: '\u2191',
} as const;

export const DAILY_EXTREMES = {
  // TemperatureGauge whiskers: H {high.toFixed(0)}° / L {low.toFixed(0)}°
  outsideTempHigh: '81',
  outsideTempLow: '68',
} as const;

/** Number of driver options in the driver selection dropdown. */
export const DRIVER_COUNT = 7;

/** Base URL for API calls within tests. */
export const API_BASE = 'http://localhost:8765';

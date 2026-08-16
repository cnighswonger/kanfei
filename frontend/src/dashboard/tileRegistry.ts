/**
 * Tile catalog: id → definition.  Placement lives in the per-persona
 * layout components under ``dashboard/layouts/``; this file is
 * catalog-only per Design's FIXED-LAYOUTS.md.
 */

export interface TileDefinition {
  id: string;
  label: string;
  category:
    | "temperature"
    | "atmosphere"
    | "wind"
    | "rain"
    | "solar"
    | "status"
    | "forecast"
    | "almanac";
  requiresSolar?: boolean;
  sensor?: string;
  chartLabel?: string;
  chartUnit?: string;
}

export const TILE_REGISTRY: Record<string, TileDefinition> = {
  "outside-temp": {
    id: "outside-temp",
    label: "Outside Temperature",
    category: "temperature",
    sensor: "outside_temp",
    chartLabel: "Outside Temperature",
    chartUnit: "°F",
  },
  "inside-temp": {
    id: "inside-temp",
    label: "Inside Temperature",
    category: "temperature",
    sensor: "inside_temp",
    chartLabel: "Inside Temperature",
    chartUnit: "°F",
  },
  barometer: {
    id: "barometer",
    label: "Barometer",
    category: "atmosphere",
    sensor: "barometer",
    chartLabel: "Barometer",
    chartUnit: "inHg",
  },
  wind: {
    id: "wind",
    label: "Wind",
    category: "wind",
    sensor: "wind_speed",
    chartLabel: "Wind Speed",
    chartUnit: "mph",
  },
  "outside-humidity": {
    id: "outside-humidity",
    label: "Outside Humidity",
    category: "atmosphere",
    sensor: "outside_humidity",
    chartLabel: "Outside Humidity",
    chartUnit: "%",
  },
  "inside-humidity": {
    id: "inside-humidity",
    label: "Inside Humidity",
    category: "atmosphere",
    sensor: "inside_humidity",
    chartLabel: "Inside Humidity",
    chartUnit: "%",
  },
  rain: {
    id: "rain",
    label: "Rain",
    category: "rain",
    sensor: "rain_total",
    chartLabel: "Rain",
    chartUnit: "in",
  },
  "solar-uv": {
    id: "solar-uv",
    label: "Solar & UV",
    category: "solar",
    requiresSolar: true,
    sensor: "solar_radiation",
    chartLabel: "Solar Radiation",
    chartUnit: "W/m²",
  },
  "current-conditions": {
    id: "current-conditions",
    label: "Derived Conditions",
    category: "status",
  },
  "station-status": {
    id: "station-status",
    label: "Station Status",
    category: "status",
  },
  "history-chart": {
    id: "history-chart",
    label: "24 h temperature & dew point",
    category: "temperature",
  },
  "rainfall-hourly": {
    id: "rainfall-hourly",
    label: "Rainfall by hour",
    category: "rain",
  },
  almanac: {
    id: "almanac",
    label: "Almanac",
    category: "almanac",
  },
  "zambretti-forecast": {
    id: "zambretti-forecast",
    label: "Zambretti forecast",
    category: "forecast",
  },
};

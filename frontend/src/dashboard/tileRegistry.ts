/**
 * Tile registry: the single source of truth for dashboard tile definitions,
 * the default layout, and persistence types.
 */

// --- Types ---

export const GRID_COLUMNS = 12;
export const DEFAULT_COL_SPAN = 2;
export const GAP = 16;

export interface TileDefinition {
  id: string;
  label: string;
  category: "temperature" | "atmosphere" | "wind" | "rain" | "solar" | "status";
  minColSpan: number;
  requiresSolar?: boolean;
  hasFlipTile: boolean;
  sensor?: string;
  chartLabel?: string;
  chartUnit?: string;
}

export interface TilePlacement {
  tileId: string;
  colSpan?: number;
  /** Wind tile display mode: compass (default) or rose. */
  windDisplay?: "compass" | "rose";
}

export interface DashboardLayout {
  version: number;
  tiles: TilePlacement[];
}

// --- Registry ---

export const TILE_REGISTRY: Record<string, TileDefinition> = {
  "outside-temp": {
    id: "outside-temp",
    label: "Outside Temperature",
    category: "temperature",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "outside_temp",
    chartLabel: "Outside Temperature",
    chartUnit: "\u00B0F",
  },
  "inside-temp": {
    id: "inside-temp",
    label: "Inside Temperature",
    category: "temperature",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "inside_temp",
    chartLabel: "Inside Temperature",
    chartUnit: "\u00B0F",
  },
  barometer: {
    id: "barometer",
    label: "Barometer",
    category: "atmosphere",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "barometer",
    chartLabel: "Barometer",
    chartUnit: "inHg",
  },
  wind: {
    id: "wind",
    label: "Wind",
    category: "wind",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "wind_speed",
    chartLabel: "Wind Speed",
    chartUnit: "mph",
  },
  "outside-humidity": {
    id: "outside-humidity",
    label: "Outside Humidity",
    category: "atmosphere",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "outside_humidity",
    chartLabel: "Outside Humidity",
    chartUnit: "%",
  },
  "inside-humidity": {
    id: "inside-humidity",
    label: "Inside Humidity",
    category: "atmosphere",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "inside_humidity",
    chartLabel: "Inside Humidity",
    chartUnit: "%",
  },
  rain: {
    id: "rain",
    label: "Rain",
    category: "rain",
    minColSpan: 2,
    hasFlipTile: true,
    sensor: "rain_total",
    chartLabel: "Rain",
    chartUnit: "in",
  },
  "solar-uv": {
    id: "solar-uv",
    label: "Solar & UV",
    category: "solar",
    minColSpan: 2,
    requiresSolar: true,
    hasFlipTile: true,
    sensor: "solar_radiation",
    chartLabel: "Solar Radiation",
    chartUnit: "W/m\u00B2",
  },
  "current-conditions": {
    id: "current-conditions",
    label: "Derived Conditions",
    category: "status",
    minColSpan: 2,
    hasFlipTile: false,
  },
  "station-status": {
    id: "station-status",
    label: "Station Status",
    category: "status",
    minColSpan: 4,
    hasFlipTile: false,
  },
};

// --- Default layout (matches the current hardcoded Dashboard.tsx) ---

export const LAYOUT_VERSION = 2;

export const DEFAULT_LAYOUT: DashboardLayout = {
  version: 2,
  tiles: [
    { tileId: "outside-temp" },
    { tileId: "inside-temp" },
    { tileId: "barometer" },
    { tileId: "wind" },
    { tileId: "outside-humidity" },
    { tileId: "inside-humidity" },
    { tileId: "rain" },
    { tileId: "solar-uv" },
    { tileId: "current-conditions" },
    { tileId: "station-status", colSpan: 12 },
  ],
};

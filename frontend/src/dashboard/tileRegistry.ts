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
  category: "temperature" | "atmosphere" | "wind" | "rain" | "solar" | "status" | "forecast" | "almanac";
  minColSpan: number;
  requiresSolar?: boolean;
  hasFlipTile: boolean;
  sensor?: string;
  chartLabel?: string;
  chartUnit?: string;
}

/**
 * Row unit for the dashboard grid.  Each 1u = 8px, so a tile with
 * ``rowSpan: 40`` occupies a 320px-tall cell.  Small enough to allow
 * fine-grained composition (a 4-row ledger vs a 300px dial can sit
 * side by side at their own natural heights); large enough that
 * layouts don't need three-digit spans.
 *
 * Per REVIEW-02: the pre-refactor grid had no ``rowSpan`` at all, so
 * every tile in a row was stretched to the tallest cell's height.
 * This unit + ``TilePlacement.rowSpan`` gives layouts an explicit
 * height axis to compose against.
 */
export const GRID_ROW_UNIT_PX = 8;

export interface TilePlacement {
  tileId: string;
  colSpan?: number;
  /**
   * Height in ``GRID_ROW_UNIT_PX``-multiples.  Optional — tiles that
   * omit this get ``DEFAULT_ROW_SPAN`` (36u = 288px), which is a
   * reasonable size for most single-metric gauge tiles.  Layouts that
   * need a taller dial or a shorter table override explicitly.
   */
  rowSpan?: number;
  /** Wind tile display mode: compass (default) or rose. */
  windDisplay?: "compass" | "rose";
}

export const DEFAULT_ROW_SPAN = 36;

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
  // Four new tiles per Design's REVIEW-02.  Registered so persona
  // layouts can place them; not yet added to any default layout in
  // this PR — that belongs to PR 24 (persona-default layout rewrite).
  "history-chart": {
    id: "history-chart",
    label: "24 h temperature & dew point",
    category: "temperature",
    minColSpan: 6,
    hasFlipTile: false,
  },
  "rainfall-hourly": {
    id: "rainfall-hourly",
    label: "Rainfall by hour",
    category: "rain",
    minColSpan: 6,
    hasFlipTile: false,
  },
  "almanac": {
    id: "almanac",
    label: "Almanac",
    category: "almanac",
    minColSpan: 3,
    hasFlipTile: false,
  },
  "zambretti-forecast": {
    id: "zambretti-forecast",
    label: "Zambretti forecast",
    category: "forecast",
    minColSpan: 3,
    hasFlipTile: false,
  },
};

// --- Default layouts ---
//
// Personas each carry a default tile set that shapes the FIRST-visit
// dashboard for a user with no saved layout.  A saved layout — the
// user's own arrangement — always wins over the persona default; the
// persona only sets the starting point and provides a "Reset to
// persona default" target.
//
// PR 24 collapses all three persona defaults onto the mock's 8/4
// composition (per Design REVIEW-02): a wide left column of hero +
// derived + chart + ledgers + hourly, and a narrow right column of
// barometer + wind + almanac + status.  Individual personas can be
// re-differentiated later; the fixed-per-persona + user-custom
// approach is Chris's parked fallback if drag-to-arrange proves to
// be the wrong lever.
//
// Row-height budget (in ``GRID_ROW_UNIT_PX`` = 8-px units), so the
// two columns line up cleanly with no CSS-grid gaps:
//
//   left 8 columns          right 4 columns
//   ─────────────────────   ─────────────────────
//   hero + derived : 30     barometer      : 30
//   history-chart  : 30     wind           : 30
//   rain + solar   : 22     almanac        : 22
//   rainfall-hourly: 20     station-status : 20
//   total: 102 units × 8px  total: 102 units × 8px

export const LAYOUT_VERSION = 2;

const MOCK_COMPOSITION: TilePlacement[] = [
  { tileId: "outside-temp", colSpan: 3, rowSpan: 30 },
  { tileId: "current-conditions", colSpan: 5, rowSpan: 30 },
  { tileId: "barometer", colSpan: 4, rowSpan: 30 },
  { tileId: "history-chart", colSpan: 8, rowSpan: 30 },
  { tileId: "wind", colSpan: 4, rowSpan: 30 },
  { tileId: "rain", colSpan: 4, rowSpan: 22 },
  { tileId: "solar-uv", colSpan: 4, rowSpan: 22 },
  { tileId: "almanac", colSpan: 4, rowSpan: 22 },
  { tileId: "rainfall-hourly", colSpan: 8, rowSpan: 20 },
  { tileId: "station-status", colSpan: 4, rowSpan: 20 },
];

const EVERYDAY_LAYOUT: DashboardLayout = {
  version: 2,
  tiles: MOCK_COMPOSITION,
};

const AGRICULTURE_LAYOUT: DashboardLayout = {
  version: 2,
  tiles: MOCK_COMPOSITION,
};

const WEATHER_NERD_LAYOUT: DashboardLayout = {
  version: 2,
  tiles: MOCK_COMPOSITION,
};

export const PERSONA_LAYOUTS: Record<string, DashboardLayout> = {
  everyday: EVERYDAY_LAYOUT,
  agriculture: AGRICULTURE_LAYOUT,
  weather_nerd: WEATHER_NERD_LAYOUT,
};

/**
 * Return the default layout for a persona.  Falls back to the
 * weather-nerd (all-tiles) layout for an unrecognised persona so a
 * bad ``ui_persona`` value never leaves the dashboard empty.
 */
export function getPersonaDefaultLayout(personaKey: string): DashboardLayout {
  return PERSONA_LAYOUTS[personaKey] ?? WEATHER_NERD_LAYOUT;
}

/**
 * Backwards-compatible export for pre-persona callers.  Same shape as
 * the pre-persona default — the all-tiles weather-nerd layout — so
 * any code path that still imports ``DEFAULT_LAYOUT`` behaves exactly
 * as it did.
 */
export const DEFAULT_LAYOUT: DashboardLayout = WEATHER_NERD_LAYOUT;

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
  /**
   * Explicit grid-column start (1-based).  When set alongside
   * ``colSpan``/``rowSpan``, DashboardGrid pins the tile with
   * ``grid-column: N / span M`` / ``grid-row: N / span M`` in normal
   * mode.  Persona defaults use this to compose the mock layout; user
   * edits (reorder / resize / add / remove) drop it so drag falls back
   * to auto-placement.  Absent = auto-placement.
   */
  gridColStart?: number;
  gridRowStart?: number;
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
// Row-span budget on the 8-px unit grid — the two column stacks each
// sum to 102 units so left and right line up cleanly with no
// auto-placement gaps:
//
//   left 8 columns          right 4 columns
//   ─────────────────────   ─────────────────────
//   hero + derived : 30     barometer      : 30
//   history-chart  : 30     wind           : 30
//   rain + solar   : 22     almanac        : 22
//   rainfall-hourly: 20     station-status : 20

export const LAYOUT_VERSION = 2;

// Explicit positioning eliminates the auto-placement gap that made
// hero and derived-conditions stretch to match barometer's height.
// Row bands (8-px units):
//   rows 1-26   hero + derived (208 px)
//   rows 27-56  history-chart (240 px) | barometer spans 1-56 (448 px)
//   rows 57-78  rain + solar + wind (176 px)
//   rows 79-98  rainfall-hourly + almanac (160 px)
//   rows 99-108 station-status footer (80 px, full width)
const MOCK_COMPOSITION: TilePlacement[] = [
  { tileId: "outside-temp",       colSpan: 3,  rowSpan: 26, gridColStart: 1, gridRowStart: 1  },
  { tileId: "current-conditions", colSpan: 5,  rowSpan: 26, gridColStart: 4, gridRowStart: 1  },
  { tileId: "barometer",          colSpan: 4,  rowSpan: 56, gridColStart: 9, gridRowStart: 1  },
  { tileId: "history-chart",      colSpan: 8,  rowSpan: 30, gridColStart: 1, gridRowStart: 27 },
  { tileId: "rain",               colSpan: 4,  rowSpan: 22, gridColStart: 1, gridRowStart: 57 },
  { tileId: "solar-uv",           colSpan: 4,  rowSpan: 22, gridColStart: 5, gridRowStart: 57 },
  { tileId: "wind",               colSpan: 4,  rowSpan: 22, gridColStart: 9, gridRowStart: 57 },
  { tileId: "rainfall-hourly",    colSpan: 8,  rowSpan: 20, gridColStart: 1, gridRowStart: 79 },
  { tileId: "almanac",            colSpan: 4,  rowSpan: 20, gridColStart: 9, gridRowStart: 79 },
  { tileId: "station-status",     colSpan: 12, rowSpan: 10, gridColStart: 1, gridRowStart: 99 },
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

/**
 * Field-level search index for Settings.
 *
 * Each entry is a searchable term paired with the ``sectionId`` of the
 * rail section that holds it.  Section ids for the three tabs with
 * sub-sections use the ``<tab>__<slug>`` convention (see
 * ``railGroups`` in ``Settings.tsx``): ``station__hardware``,
 * ``site_units__location``, ``appearance__theme`` etc.  For every
 * other tab the section id IS the tab id (``services``, ``bots``, …).
 * ``computeMatches`` returns a ``Map<sectionId, number>`` so the rail
 * can attach the tally to the exact section the user should click
 * rather than to the parent group.
 *
 * The index is hand-curated: bootstrapped from the ``<h3
 * sectionTitle>`` and ``<label labelStyle>`` texts in ``Settings.tsx``
 * per tab, augmented for the extracted sub-components (Database,
 * Backup, System) and for aliases users are likely to type ("GPS" for
 * Location, "rain gauge" for the rain section).  When a new field
 * lands, add its label here so search picks it up.
 *
 * Match rule: case-insensitive substring on the query.  Query is
 * pre-lowercased in ``computeMatches``.
 */

export interface SearchEntry {
  /** Rail section id — either a plain tab id, or ``<tab>__<slug>``. */
  sectionId: string;
  /** Human-readable term the user might search for. */
  term: string;
}

export const SETTINGS_SEARCH_INDEX: SearchEntry[] = [
  // ── station · optional features ───────────────────────────────────
  { sectionId: "station__optional", term: "Optional Features" },
  { sectionId: "station__optional", term: "Enable AI Nowcast" },
  { sectionId: "station__optional", term: "Enable Spray Advisor" },
  { sectionId: "station__optional", term: "Anthropic Admin API Key" },
  { sectionId: "station__optional", term: "Usage budget" },
  { sectionId: "station__optional", term: "Monthly budget USD" },
  { sectionId: "station__optional", term: "Auto-pause" },

  // ── station · hardware ────────────────────────────────────────────
  { sectionId: "station__hardware", term: "Station" },
  { sectionId: "station__hardware", term: "Hardware" },
  { sectionId: "station__hardware", term: "Driver Type" },
  { sectionId: "station__hardware", term: "Serial Port" },
  { sectionId: "station__hardware", term: "Baud Rate" },
  { sectionId: "station__hardware", term: "TCP Port" },
  { sectionId: "station__hardware", term: "Poll Interval" },
  { sectionId: "station__hardware", term: "Hub Serial Number" },
  { sectionId: "station__hardware", term: "Listen Port" },
  { sectionId: "station__hardware", term: "Public Droplet Relay" },
  { sectionId: "station__hardware", term: "Target URL" },
  { sectionId: "station__hardware", term: "Shared secret" },
  { sectionId: "station__hardware", term: "Public relay" },

  // ── station · console configuration ───────────────────────────────
  { sectionId: "station__console_config", term: "Console configuration" },
  { sectionId: "station__console_config", term: "Console highs and lows" },
  { sectionId: "station__console_config", term: "Reset highs" },
  { sectionId: "station__console_config", term: "Console data operations" },
  { sectionId: "station__console_config", term: "Force archive" },
  { sectionId: "station__console_config", term: "Clear daily rain" },
  { sectionId: "station__console_config", term: "Clear yearly rain" },

  // ── station · calibration & diagnostics ───────────────────────────
  { sectionId: "station__calibration", term: "Calibration" },
  { sectionId: "station__calibration", term: "Diagnostics" },
  { sectionId: "station__calibration", term: "Barometer calibration" },
  { sectionId: "station__calibration", term: "Baro offset" },
  { sectionId: "station__calibration", term: "Elevation" },
  { sectionId: "station__calibration", term: "Vantage calibration" },
  { sectionId: "station__calibration", term: "Signal quality" },
  { sectionId: "station__calibration", term: "RXCHECK" },
  { sectionId: "station__calibration", term: "Reception diagnostics" },

  // ── site & units · location ───────────────────────────────────────
  { sectionId: "site_units__location", term: "Location" },
  { sectionId: "site_units__location", term: "Latitude" },
  { sectionId: "site_units__location", term: "Longitude" },
  { sectionId: "site_units__location", term: "GPS" },
  { sectionId: "site_units__location", term: "Coordinates" },
  { sectionId: "site_units__location", term: "Elevation" },
  { sectionId: "site_units__location", term: "Console location" },
  { sectionId: "site_units__location", term: "Rain gauge" },
  { sectionId: "site_units__location", term: "Rain collector" },
  { sectionId: "site_units__location", term: "Rain season" },
  { sectionId: "site_units__location", term: "Season rain" },

  // ── site & units · units ──────────────────────────────────────────
  { sectionId: "site_units__units", term: "Units" },
  { sectionId: "site_units__units", term: "Temperature unit" },
  { sectionId: "site_units__units", term: "Fahrenheit" },
  { sectionId: "site_units__units", term: "Celsius" },
  { sectionId: "site_units__units", term: "Pressure unit" },
  { sectionId: "site_units__units", term: "inHg" },
  { sectionId: "site_units__units", term: "hPa" },
  { sectionId: "site_units__units", term: "mbar" },
  { sectionId: "site_units__units", term: "Wind speed unit" },
  { sectionId: "site_units__units", term: "mph" },
  { sectionId: "site_units__units", term: "kts" },
  { sectionId: "site_units__units", term: "km/h" },
  { sectionId: "site_units__units", term: "Rain unit" },
  { sectionId: "site_units__units", term: "Inches" },
  { sectionId: "site_units__units", term: "mm" },
  { sectionId: "site_units__units", term: "Solar energy unit" },
  { sectionId: "site_units__units", term: "MJ/m²" },
  { sectionId: "site_units__units", term: "kWh/m²" },

  // ── site & units · timezone ───────────────────────────────────────
  { sectionId: "site_units__timezone", term: "Timezone" },

  // ── appearance ────────────────────────────────────────────────────
  // Design v32 review collapsed the two sub-sections (theme +
  // backgrounds) into a single panel with three cards (Theme + Persona
  // + Backgrounds); every entry here points at the leaf ``appearance``
  // rail row.
  { sectionId: "appearance", term: "Theme" },
  { sectionId: "appearance", term: "Dark theme" },
  { sectionId: "appearance", term: "Light theme" },
  { sectionId: "appearance", term: "Mammoth" },
  { sectionId: "appearance", term: "Glaisher" },
  { sectionId: "appearance", term: "Classic" },
  { sectionId: "appearance", term: "Custom theme" },
  { sectionId: "appearance", term: "Font scale" },
  { sectionId: "appearance", term: "Display" },
  { sectionId: "appearance", term: "Persona" },
  { sectionId: "appearance", term: "Everyday" },
  { sectionId: "appearance", term: "Agriculture" },
  { sectionId: "appearance", term: "Weather Nerd" },
  { sectionId: "appearance", term: "Backgrounds" },
  { sectionId: "appearance", term: "Weather background" },
  { sectionId: "appearance", term: "Background image" },
  { sectionId: "appearance", term: "Custom images" },
  { sectionId: "appearance", term: "Intensity" },
  { sectionId: "appearance", term: "Transparency" },

  // ── services (integrations) ──────────────────────────────────────
  { sectionId: "services", term: "Weather Underground" },
  { sectionId: "services", term: "WU Station ID" },
  { sectionId: "services", term: "WU Station Key" },
  { sectionId: "services", term: "CWOP" },
  { sectionId: "services", term: "APRS" },
  { sectionId: "services", term: "CWOP callsign" },
  { sectionId: "services", term: "Upload Interval" },
  { sectionId: "services", term: "METAR Station" },
  { sectionId: "services", term: "Channel Mute" },
  { sectionId: "services", term: "Sensor reporting" },
  { sectionId: "services", term: "Map tile layer" },
  { sectionId: "services", term: "Default map layer" },
  { sectionId: "services", term: "Isobar interval" },
  { sectionId: "services", term: "Max station radius" },

  // ── bots ─────────────────────────────────────────────────────────
  { sectionId: "bots", term: "Telegram Bot" },
  { sectionId: "bots", term: "Telegram Token" },
  { sectionId: "bots", term: "Telegram Chat ID" },
  { sectionId: "bots", term: "Discord Bot" },
  { sectionId: "bots", term: "Discord Token" },
  { sectionId: "bots", term: "Discord Guild ID" },
  { sectionId: "bots", term: "Discord Channel ID" },
  { sectionId: "bots", term: "Scheduled conditions push" },
  { sectionId: "bots", term: "Bot commands" },
  { sectionId: "bots", term: "Bot notifications" },

  // ── alerts ───────────────────────────────────────────────────────
  { sectionId: "alerts", term: "Alerts" },
  { sectionId: "alerts", term: "Alert thresholds" },
  { sectionId: "alerts", term: "Alert cooldown" },
  { sectionId: "alerts", term: "Alert condition" },
  { sectionId: "alerts", term: "Sensor threshold" },
  { sectionId: "alerts", term: "Notifications" },

  // ── nowcast ──────────────────────────────────────────────────────
  { sectionId: "nowcast", term: "AI Nowcast" },
  { sectionId: "nowcast", term: "Nowcast Mode" },
  { sectionId: "nowcast", term: "Nowcast Update Interval" },
  { sectionId: "nowcast", term: "WU API Key" },
  { sectionId: "nowcast", term: "ASOS Stations" },
  { sectionId: "nowcast", term: "WU Stations" },
  { sectionId: "nowcast", term: "APRS Stations" },
  { sectionId: "nowcast", term: "Grok Model" },
  { sectionId: "nowcast", term: "OpenAI Model" },
  { sectionId: "nowcast", term: "Anthropic Model" },
  { sectionId: "nowcast", term: "Forecast Horizon" },
  { sectionId: "nowcast", term: "Nearby Station Radius" },

  // ── spray ────────────────────────────────────────────────────────
  { sectionId: "spray", term: "Spray Advisor" },
  { sectionId: "spray", term: "Spray product" },
  { sectionId: "spray", term: "Wind limit" },
  { sectionId: "spray", term: "Temperature limit" },
  { sectionId: "spray", term: "Humidity limit" },
  { sectionId: "spray", term: "Delta-T" },

  // ── usage ────────────────────────────────────────────────────────
  { sectionId: "usage", term: "API usage" },
  { sectionId: "usage", term: "Cost" },
  { sectionId: "usage", term: "Budget" },
  { sectionId: "usage", term: "Local usage" },

  // ── database ─────────────────────────────────────────────────────
  { sectionId: "database", term: "Database" },
  { sectionId: "database", term: "DB stats" },
  { sectionId: "database", term: "Purge readings" },
  { sectionId: "database", term: "Purge table" },
  { sectionId: "database", term: "Compact" },
  { sectionId: "database", term: "Danger zone" },
  { sectionId: "database", term: "Delete database" },
  { sectionId: "database", term: "Export" },
  { sectionId: "database", term: "CSV export" },
  { sectionId: "database", term: "SQL dump" },

  // ── backup ───────────────────────────────────────────────────────
  { sectionId: "backup", term: "Backup" },
  { sectionId: "backup", term: "Backup schedule" },
  { sectionId: "backup", term: "Backup interval" },
  { sectionId: "backup", term: "Backup retention" },
  { sectionId: "backup", term: "Backup path" },
  { sectionId: "backup", term: "Restore backup" },

  // ── system ───────────────────────────────────────────────────────
  { sectionId: "system", term: "System" },
  { sectionId: "system", term: "Password" },
  { sectionId: "system", term: "Change password" },
  { sectionId: "system", term: "API keys" },
  { sectionId: "system", term: "Sign-in" },
  { sectionId: "system", term: "Logout" },
  { sectionId: "system", term: "Log level" },
  { sectionId: "system", term: "Logs" },
  { sectionId: "system", term: "System info" },
  { sectionId: "system", term: "Version" },
];

/**
 * Count matches per section (rail section id).  Returns a map from
 * section id → number of matching index entries.  Missing keys mean
 * zero matches.  Empty / whitespace-only query returns an empty map.
 */
export function computeMatches(query: string): Map<string, number> {
  const q = query.trim().toLowerCase();
  const out = new Map<string, number>();
  if (!q) return out;
  for (const { sectionId, term } of SETTINGS_SEARCH_INDEX) {
    if (term.toLowerCase().includes(q)) {
      out.set(sectionId, (out.get(sectionId) ?? 0) + 1);
    }
  }
  return out;
}

/**
 * Total match count across all sections.  Used for the "N matches"
 * line under the search input.
 */
export function totalMatches(matches: Map<string, number>): number {
  let n = 0;
  for (const v of matches.values()) n += v;
  return n;
}

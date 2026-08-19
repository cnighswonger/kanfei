/**
 * Field-level search index for Settings.
 *
 * Each entry is a searchable term paired with the tab id whose panel
 * body contains it.  A query counts terms per tab and the SectionRail
 * displays the tally as a match badge.  The rail's ``section id`` is
 * the tab id, so the index maps 1-1 to the rail sections that Phase 1
 * already exposes.
 *
 * The index is hand-curated: bootstrapped from the ``<h3 sectionTitle>``
 * and ``<label labelStyle>`` texts in ``Settings.tsx`` per tab, then
 * augmented for the extracted sub-components (Database, Backup,
 * System) and for aliases users are likely to type ("GPS" for
 * Location, "rain gauge" for the rain section).  When a new field
 * lands, add its label here so search picks it up — a curated map
 * beats a full text scrape because the scrape misses aliases and
 * catches noise like button labels and confirmation words.
 *
 * Match rule: case-insensitive substring on the query.  Query is
 * pre-lowercased in ``computeMatches``.
 */

export interface SearchEntry {
  /** Rail section id (== ``activeTab`` value). */
  tab: string;
  /** Human-readable term the user might search for. */
  term: string;
}

export const SETTINGS_SEARCH_INDEX: SearchEntry[] = [
  // ── station ──────────────────────────────────────────────────────
  { tab: "station", term: "Optional Features" },
  { tab: "station", term: "Enable AI Nowcast" },
  { tab: "station", term: "Enable Spray Advisor" },
  { tab: "station", term: "Anthropic Admin API Key" },
  { tab: "station", term: "Usage budget" },
  { tab: "station", term: "Monthly budget USD" },
  { tab: "station", term: "Auto-pause" },
  { tab: "station", term: "Hardware" },
  { tab: "station", term: "Station" },
  { tab: "station", term: "Driver Type" },
  { tab: "station", term: "Serial Port" },
  { tab: "station", term: "Baud Rate" },
  { tab: "station", term: "TCP Port" },
  { tab: "station", term: "Poll Interval" },
  { tab: "station", term: "Hub Serial Number" },
  { tab: "station", term: "Listen Port" },
  { tab: "station", term: "Public Droplet Relay" },
  { tab: "station", term: "Target URL" },
  { tab: "station", term: "Shared secret" },
  { tab: "station", term: "Public relay" },
  { tab: "station", term: "Console configuration" },
  { tab: "station", term: "Calibration" },
  { tab: "station", term: "Diagnostics" },
  { tab: "station", term: "Barometer calibration" },
  { tab: "station", term: "Baro offset" },
  { tab: "station", term: "Elevation" },
  { tab: "station", term: "Rain collector" },
  { tab: "station", term: "Rain gauge" },
  { tab: "station", term: "Season rain" },
  { tab: "station", term: "Console highs and lows" },
  { tab: "station", term: "Reset highs" },
  { tab: "station", term: "Console location" },
  { tab: "station", term: "Signal quality" },
  { tab: "station", term: "RXCHECK" },
  { tab: "station", term: "Vantage calibration" },
  { tab: "station", term: "Console data operations" },

  // ── site_units ───────────────────────────────────────────────────
  { tab: "site_units", term: "Location" },
  { tab: "site_units", term: "Latitude" },
  { tab: "site_units", term: "Longitude" },
  { tab: "site_units", term: "GPS" },
  { tab: "site_units", term: "Coordinates" },
  { tab: "site_units", term: "Elevation" },
  { tab: "site_units", term: "Units" },
  { tab: "site_units", term: "Temperature unit" },
  { tab: "site_units", term: "Fahrenheit" },
  { tab: "site_units", term: "Celsius" },
  { tab: "site_units", term: "Pressure unit" },
  { tab: "site_units", term: "inHg" },
  { tab: "site_units", term: "hPa" },
  { tab: "site_units", term: "mbar" },
  { tab: "site_units", term: "Wind speed unit" },
  { tab: "site_units", term: "mph" },
  { tab: "site_units", term: "kts" },
  { tab: "site_units", term: "km/h" },
  { tab: "site_units", term: "Rain unit" },
  { tab: "site_units", term: "Inches" },
  { tab: "site_units", term: "mm" },
  { tab: "site_units", term: "Solar energy unit" },
  { tab: "site_units", term: "MJ/m²" },
  { tab: "site_units", term: "kWh/m²" },
  { tab: "site_units", term: "Timezone" },

  // ── appearance ───────────────────────────────────────────────────
  { tab: "appearance", term: "Theme" },
  { tab: "appearance", term: "Persona" },
  { tab: "appearance", term: "Dark theme" },
  { tab: "appearance", term: "Light theme" },
  { tab: "appearance", term: "Mammoth" },
  { tab: "appearance", term: "Glaisher" },
  { tab: "appearance", term: "Classic" },
  { tab: "appearance", term: "Weather background" },
  { tab: "appearance", term: "Background image" },
  { tab: "appearance", term: "Custom images" },
  { tab: "appearance", term: "Font scale" },
  { tab: "appearance", term: "Display" },

  // ── services (integrations) ──────────────────────────────────────
  { tab: "services", term: "Weather Underground" },
  { tab: "services", term: "WU Station ID" },
  { tab: "services", term: "WU Station Key" },
  { tab: "services", term: "CWOP" },
  { tab: "services", term: "APRS" },
  { tab: "services", term: "CWOP callsign" },
  { tab: "services", term: "Upload Interval" },
  { tab: "services", term: "METAR Station" },
  { tab: "services", term: "Channel Mute" },
  { tab: "services", term: "Sensor reporting" },
  { tab: "services", term: "Map tile layer" },
  { tab: "services", term: "Default map layer" },
  { tab: "services", term: "Isobar interval" },
  { tab: "services", term: "Max station radius" },

  // ── bots ─────────────────────────────────────────────────────────
  { tab: "bots", term: "Telegram Bot" },
  { tab: "bots", term: "Telegram Token" },
  { tab: "bots", term: "Telegram Chat ID" },
  { tab: "bots", term: "Discord Bot" },
  { tab: "bots", term: "Discord Token" },
  { tab: "bots", term: "Discord Guild ID" },
  { tab: "bots", term: "Discord Channel ID" },
  { tab: "bots", term: "Scheduled conditions push" },
  { tab: "bots", term: "Bot commands" },
  { tab: "bots", term: "Bot notifications" },

  // ── alerts ───────────────────────────────────────────────────────
  { tab: "alerts", term: "Alerts" },
  { tab: "alerts", term: "Alert thresholds" },
  { tab: "alerts", term: "Alert cooldown" },
  { tab: "alerts", term: "Alert condition" },
  { tab: "alerts", term: "Sensor threshold" },
  { tab: "alerts", term: "Notifications" },

  // ── nowcast ──────────────────────────────────────────────────────
  { tab: "nowcast", term: "AI Nowcast" },
  { tab: "nowcast", term: "Nowcast Mode" },
  { tab: "nowcast", term: "Nowcast Update Interval" },
  { tab: "nowcast", term: "WU API Key" },
  { tab: "nowcast", term: "ASOS Stations" },
  { tab: "nowcast", term: "WU Stations" },
  { tab: "nowcast", term: "APRS Stations" },
  { tab: "nowcast", term: "Grok Model" },
  { tab: "nowcast", term: "OpenAI Model" },
  { tab: "nowcast", term: "Anthropic Model" },
  { tab: "nowcast", term: "Forecast Horizon" },
  { tab: "nowcast", term: "Nearby Station Radius" },

  // ── spray ────────────────────────────────────────────────────────
  { tab: "spray", term: "Spray Advisor" },
  { tab: "spray", term: "Spray product" },
  { tab: "spray", term: "Wind limit" },
  { tab: "spray", term: "Temperature limit" },
  { tab: "spray", term: "Humidity limit" },
  { tab: "spray", term: "Delta-T" },

  // ── usage ────────────────────────────────────────────────────────
  { tab: "usage", term: "API usage" },
  { tab: "usage", term: "Cost" },
  { tab: "usage", term: "Budget" },
  { tab: "usage", term: "Local usage" },

  // ── database ─────────────────────────────────────────────────────
  { tab: "database", term: "Database" },
  { tab: "database", term: "DB stats" },
  { tab: "database", term: "Purge readings" },
  { tab: "database", term: "Purge table" },
  { tab: "database", term: "Compact" },
  { tab: "database", term: "Danger zone" },
  { tab: "database", term: "Delete database" },
  { tab: "database", term: "Export" },
  { tab: "database", term: "CSV export" },
  { tab: "database", term: "SQL dump" },

  // ── backup ───────────────────────────────────────────────────────
  { tab: "backup", term: "Backup" },
  { tab: "backup", term: "Backup schedule" },
  { tab: "backup", term: "Backup interval" },
  { tab: "backup", term: "Backup retention" },
  { tab: "backup", term: "Backup path" },
  { tab: "backup", term: "Restore backup" },

  // ── system ───────────────────────────────────────────────────────
  { tab: "system", term: "System" },
  { tab: "system", term: "Password" },
  { tab: "system", term: "Change password" },
  { tab: "system", term: "API keys" },
  { tab: "system", term: "Sign-in" },
  { tab: "system", term: "Logout" },
  { tab: "system", term: "Log level" },
  { tab: "system", term: "Logs" },
  { tab: "system", term: "System info" },
  { tab: "system", term: "Version" },
];

/**
 * Count matches per tab.  Returns a map from tab id → number of matching
 * index entries.  Missing keys mean zero matches.  An empty / whitespace-
 * only query returns an empty map (the SaveBar interprets that as "no
 * badges rendered").
 */
export function computeMatches(query: string): Map<string, number> {
  const q = query.trim().toLowerCase();
  const out = new Map<string, number>();
  if (!q) return out;
  for (const { tab, term } of SETTINGS_SEARCH_INDEX) {
    if (term.toLowerCase().includes(q)) {
      out.set(tab, (out.get(tab) ?? 0) + 1);
    }
  }
  return out;
}

/**
 * Total match count across all tabs.  Used for the "N matches" line
 * under the search input.
 */
export function totalMatches(matches: Map<string, number>): number {
  let n = 0;
  for (const v of matches.values()) n += v;
  return n;
}

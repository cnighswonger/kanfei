/**
 * UI preference persistence — localStorage cache + backend config as source of truth.
 *
 * readUIPref()  — synchronous read from localStorage (no FOUC)
 * writeUIPref() — writes to localStorage + async PUT to backend
 * syncUIPrefs() — one-time fetch from backend, reconciles with localStorage,
 *                 migrates old keys on first run after upgrade
 */

import { fetchConfig, updateConfig } from "../api/client.ts";

// ---------------------------------------------------------------------------
// Defaults — must match backend _DEFAULTS in config.py
// ---------------------------------------------------------------------------

const UI_DEFAULTS: Record<string, string> = {
  ui_sidebar_collapsed: "false",
  ui_theme: "dark",
  ui_timezone: "auto",
  ui_weather_bg_enabled: "true",
  ui_weather_bg_intensity: "30",
  ui_weather_bg_transparency: "15",
  ui_dashboard_layout: "",
};

// ---------------------------------------------------------------------------
// Old localStorage key → new backend key mapping (one-time migration)
// ---------------------------------------------------------------------------

interface MigrationEntry {
  newKey: string;
  transform?: (v: string) => string;
}

const MIGRATION_MAP: Record<string, MigrationEntry> = {
  "sidebar-collapsed": { newKey: "ui_sidebar_collapsed" },
  "davis-wx-theme": { newKey: "ui_theme" },
  "davis-wx-timezone": { newKey: "ui_timezone" },
  "davis-wx-weather-bg": {
    newKey: "ui_weather_bg_enabled",
    transform: (v) => (v === "off" ? "false" : "true"),
  },
  "davis-wx-weather-bg-intensity": { newKey: "ui_weather_bg_intensity" },
  "davis-wx-weather-bg-transparency": { newKey: "ui_weather_bg_transparency" },
  "davis-wx-dashboard-layout": { newKey: "ui_dashboard_layout" },
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Synchronous read from localStorage (used for initial render). */
export function readUIPref(key: string, defaultValue: string): string {
  try {
    const v = localStorage.getItem(key);
    if (v !== null) return v;
  } catch {
    /* localStorage unavailable */
  }
  return defaultValue;
}

/** Write to localStorage (sync) + fire-and-forget PUT to backend. */
export function writeUIPref(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* localStorage unavailable */
  }
  updateConfig([{ key, value }]).catch((err) => {
    console.warn(`[uiPrefs] failed to save ${key} to backend:`, err);
  });
}

// ---------------------------------------------------------------------------
// Sync / migration (runs once per app load)
// ---------------------------------------------------------------------------

type PrefsMap = Record<string, string>;

let syncPromise: Promise<PrefsMap> | null = null;

/**
 * Fetch all config from backend, reconcile with localStorage, and migrate
 * old keys if needed.  Deduplicated — only the first call does real work;
 * subsequent calls return the same promise.
 */
export function syncUIPrefs(): Promise<PrefsMap> {
  if (!syncPromise) {
    syncPromise = _doSync();
  }
  return syncPromise;
}

async function _doSync(): Promise<PrefsMap> {
  const resolved: PrefsMap = {};

  try {
    const items = await fetchConfig();
    const backendMap: Record<string, string> = {};
    for (const item of items) {
      if (typeof item.key === "string" && item.key.startsWith("ui_")) {
        backendMap[item.key] = String(item.value);
      }
    }

    // --- Migration: push old localStorage values to backend if needed ---
    const toMigrate: { key: string; value: string }[] = [];

    for (const [oldKey, { newKey, transform }] of Object.entries(MIGRATION_MAP)) {
      try {
        const oldValue = localStorage.getItem(oldKey);
        if (oldValue === null) continue;

        const converted = transform ? transform(oldValue) : oldValue;
        const backendValue = backendMap[newKey];
        const defaultValue = UI_DEFAULTS[newKey];

        // Only migrate if backend still has the default (hasn't been set yet)
        if (backendValue === undefined || backendValue === defaultValue) {
          if (converted !== defaultValue) {
            toMigrate.push({ key: newKey, value: converted });
            backendMap[newKey] = converted;
          }
        }

        // Clean up old key
        localStorage.removeItem(oldKey);
      } catch {
        /* ignore individual key errors */
      }
    }

    if (toMigrate.length > 0) {
      await updateConfig(toMigrate).catch((err) => {
        console.warn("[uiPrefs] migration push failed:", err);
      });
    }

    // --- Reconcile: backend wins, update localStorage ---
    for (const [key, defaultValue] of Object.entries(UI_DEFAULTS)) {
      const backendValue = backendMap[key] ?? defaultValue;
      resolved[key] = backendValue;
      try {
        localStorage.setItem(key, backendValue);
      } catch {
        /* ignore */
      }
    }
  } catch (err) {
    console.warn("[uiPrefs] sync failed, using localStorage values:", err);
    // Fall back to whatever localStorage has
    for (const [key, defaultValue] of Object.entries(UI_DEFAULTS)) {
      resolved[key] = readUIPref(key, defaultValue);
    }
  }

  return resolved;
}

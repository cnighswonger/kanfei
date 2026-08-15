/**
 * Dashboard layout context — manages tile arrangement and per-tile display
 * options (e.g. wind compass vs rose) with backend-persisted preferences
 * (localStorage as sync cache). Follows the same pattern as ThemeContext
 * and WeatherBackgroundContext.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import {
  type DashboardLayout,
  type TilePlacement,
  TILE_REGISTRY,
  LAYOUT_VERSION,
  GRID_COLUMNS,
  getPersonaDefaultLayout,
  PERSONA_LAYOUTS,
} from "./tileRegistry.ts";
import { readUIPref, writeUIPref, syncUIPrefs } from "../utils/uiPrefs.ts";
import { usePersona, DEFAULT_PERSONA, type Persona } from "../context/PersonaContext.tsx";

const PERSONA_PREF_KEY = "ui_persona";

function readCurrentPersonaFromStorage(): string {
  // Synchronous read for the initial layout — matches how ThemeContext
  // resolves themeName before the React tree mounts (context reads only
  // work inside components, but the initial useState computation is
  // outside the component during first render's setup).
  return readUIPref(PERSONA_PREF_KEY, DEFAULT_PERSONA);
}

/**
 * Per-persona storage key for the saved dashboard arrangement.  Each
 * persona has its own slot so a user's Everyday arrangement is
 * independent of their Agriculture arrangement — picking a persona
 * loads that persona's saved layout (or its default if unsaved), and
 * saving under one persona never touches another's.
 */
const PER_PERSONA_LAYOUT_KEY: Record<Persona, string> = {
  everyday: "ui_dashboard_layout_everyday",
  agriculture: "ui_dashboard_layout_agriculture",
  weather_nerd: "ui_dashboard_layout_weather_nerd",
};

function layoutKeyFor(persona: string): string {
  return PER_PERSONA_LAYOUT_KEY[persona as Persona]
    ?? PER_PERSONA_LAYOUT_KEY[DEFAULT_PERSONA];
}

/**
 * Legacy single-key layout from before the per-persona split.  Read
 * once at load-time and migrated into the current-persona slot.  After
 * migration, ``writeUIPref`` clears both localStorage and backend so
 * the key doesn't come back on the next syncUIPrefs pass.
 */
const LEGACY_LAYOUT_KEY = "ui_dashboard_layout";

// --- Types ---

interface DashboardLayoutContextValue {
  layout: DashboardLayout;
  editMode: boolean;
  setEditMode: (v: boolean) => void;
  reorderTiles: (fromIndex: number, toIndex: number) => void;
  addTile: (tileId: string, colSpan?: number) => void;
  removeTile: (tileId: string) => void;
  setTileColSpan: (tileId: string, colSpan: number) => void;
  setAllTilesSpan: (colSpan: number) => void;
  setTileWindDisplay: (tileId: string, mode: "compass" | "rose") => void;
  resetToDefault: () => void;
}

const DashboardLayoutContext =
  createContext<DashboardLayoutContextValue | null>(null);

// --- Persistence helpers ---

const OLD_COLUMNS_KEY = "davis-wx-dashboard-columns";

function migrateV1(
  parsed: { version: number; tiles: { tileId: string; colSpan?: number }[] },
  persona: string,
): DashboardLayout {
  // Read old columns setting for span conversion
  let oldColumns = 3;
  try {
    const v = parseInt(localStorage.getItem(OLD_COLUMNS_KEY) || "3", 10);
    if (v >= 2 && v <= 4) oldColumns = v;
  } catch {}

  const factor = Math.round(GRID_COLUMNS / oldColumns);
  const migratedTiles: TilePlacement[] = parsed.tiles
    .filter((t) => t.tileId in TILE_REGISTRY)
    .map((t) => ({
      tileId: t.tileId,
      colSpan: t.colSpan ? Math.min(t.colSpan * factor, GRID_COLUMNS) : undefined,
    }));

  // Clean up old columns key
  try { localStorage.removeItem(OLD_COLUMNS_KEY); } catch {}

  const migrated: DashboardLayout = { version: LAYOUT_VERSION, tiles: migratedTiles };
  saveLayoutForPersona(persona, migrated);
  return migrated;
}

function parseLayout(
  raw: string,
  fallback: DashboardLayout,
  persona: string,
): DashboardLayout {
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw) as DashboardLayout;

    // Migrate v1 layouts
    if (parsed.version === 1) {
      return migrateV1(parsed, persona);
    }

    // Version check — fall back if schema changed
    if (parsed.version !== LAYOUT_VERSION) return fallback;

    // Validate: strip tiles with unknown IDs
    const validTiles = parsed.tiles.filter(
      (t) => t.tileId in TILE_REGISTRY,
    );
    if (validTiles.length === 0) return fallback;

    return { version: LAYOUT_VERSION, tiles: validTiles };
  } catch {
    return fallback;
  }
}

function loadLayoutForPersona(persona: string): DashboardLayout {
  const raw = readUIPref(layoutKeyFor(persona), "");
  return parseLayout(raw, getPersonaDefaultLayout(persona), persona);
}

function saveLayoutForPersona(persona: string, layout: DashboardLayout): void {
  writeUIPref(layoutKeyFor(persona), JSON.stringify(layout));
}

/**
 * Serialized form of each built-in persona default layout.  Used by
 * the legacy-key migration to decide whether the pre-per-persona
 * value was user-arranged (worth preserving) or just a built-in
 * default (worth discarding so the persona system starts clean).
 */
const PERSONA_DEFAULT_SERIALIZED = new Set(
  Object.values(PERSONA_LAYOUTS).map((d) => JSON.stringify(d)),
);

/**
 * One-time migration from the pre-per-persona single ``ui_dashboard_layout``
 * key into a persona-specific slot.  Runs on every mount but is idempotent
 * after the first pass because ``writeUIPref(LEGACY_LAYOUT_KEY, "")``
 * clears both local and backend, so subsequent reads see an empty legacy.
 *
 * Migration rules:
 *
 * - Legacy empty → nothing to do.
 * - Legacy equals any built-in persona default → discard.  It was never
 *   customized (it's the shape a prior install seeded automatically), so
 *   preserving it would spam every persona's slot with the same default.
 * - Legacy is a real user arrangement → copy into weather_nerd's slot
 *   (pre-persona clients only had the all-tiles default, so the natural
 *   home for a customization is weather_nerd), but only if that slot is
 *   currently unset.  A user who has already saved a per-persona
 *   arrangement wins.
 *
 * Runs in the useState lazy initializer so it fires before any effect
 * or the first render's ``loadLayoutForPersona`` call.
 */
function migrateLegacyLayoutOnce(): void {
  try {
    const legacy = localStorage.getItem(LEGACY_LAYOUT_KEY);
    if (!legacy) return;
    if (!PERSONA_DEFAULT_SERIALIZED.has(legacy)) {
      const target = layoutKeyFor("weather_nerd");
      const existing = localStorage.getItem(target);
      if (!existing) {
        writeUIPref(target, legacy);
      }
    }
    writeUIPref(LEGACY_LAYOUT_KEY, "");
  } catch { /* localStorage unavailable */ }
}

// --- Provider ---

export function DashboardLayoutProvider({
  children,
}: {
  children: ReactNode;
}) {
  const { persona } = usePersona();
  const [layout, setLayoutState] = useState<DashboardLayout>(() => {
    // Legacy-key migration runs exactly once per app-load, in the
    // useState initializer so it fires before any effect and before
    // the first render reads a persona-specific slot.
    migrateLegacyLayoutOnce();
    return loadLayoutForPersona(readCurrentPersonaFromStorage());
  });
  const [editMode, setEditMode] = useState(false);

  const updateLayout = useCallback(
    (next: DashboardLayout) => {
      setLayoutState(next);
      saveLayoutForPersona(persona, next);
    },
    [persona],
  );

  const reorderTiles = useCallback(
    (fromIndex: number, toIndex: number) => {
      setLayoutState((prev) => {
        const tiles = [...prev.tiles];
        const [moved] = tiles.splice(fromIndex, 1);
        tiles.splice(toIndex, 0, moved);
        const next = { ...prev, tiles };
        saveLayoutForPersona(persona, next);
        return next;
      });
    },
    [persona],
  );

  const addTile = useCallback(
    (tileId: string, colSpan?: number) => {
      if (!(tileId in TILE_REGISTRY)) return;
      setLayoutState((prev) => {
        // Prevent duplicates
        if (prev.tiles.some((t) => t.tileId === tileId)) return prev;
        const placement: TilePlacement = { tileId };
        if (colSpan) placement.colSpan = colSpan;
        const next = { ...prev, tiles: [...prev.tiles, placement] };
        saveLayoutForPersona(persona, next);
        return next;
      });
    },
    [persona],
  );

  const removeTile = useCallback(
    (tileId: string) => {
      setLayoutState((prev) => {
        const next = {
          ...prev,
          tiles: prev.tiles.filter((t) => t.tileId !== tileId),
        };
        saveLayoutForPersona(persona, next);
        return next;
      });
    },
    [persona],
  );

  const setTileColSpan = useCallback(
    (tileId: string, colSpan: number) => {
      const def = TILE_REGISTRY[tileId];
      const min = def?.minColSpan ?? 2;
      const clamped = Math.max(min, Math.min(GRID_COLUMNS, colSpan));
      setLayoutState((prev) => {
        const next = {
          ...prev,
          tiles: prev.tiles.map((t) =>
            t.tileId === tileId ? { ...t, colSpan: clamped } : t,
          ),
        };
        saveLayoutForPersona(persona, next);
        return next;
      });
    },
    [persona],
  );

  const setAllTilesSpan = useCallback(
    (colSpan: number) => {
      setLayoutState((prev) => {
        const next = {
          ...prev,
          tiles: prev.tiles.map((t) => {
            const def = TILE_REGISTRY[t.tileId];
            const min = def?.minColSpan ?? 2;
            return { ...t, colSpan: Math.max(min, Math.min(GRID_COLUMNS, colSpan)) };
          }),
        };
        saveLayoutForPersona(persona, next);
        return next;
      });
    },
    [persona],
  );

  const setTileWindDisplay = useCallback(
    (tileId: string, mode: "compass" | "rose") => {
      setLayoutState((prev) => {
        const next = {
          ...prev,
          tiles: prev.tiles.map((t) =>
            t.tileId === tileId ? { ...t, windDisplay: mode === "compass" ? undefined : mode } : t,
          ),
        };
        saveLayoutForPersona(persona, next);
        return next;
      });
    },
    [persona],
  );

  const resetToDefault = useCallback(() => {
    updateLayout(getPersonaDefaultLayout(persona));
    setEditMode(false);
  }, [updateLayout, persona]);

  // Persona is authoritative: switching personas loads THAT persona's
  // saved layout (or its default if that slot is unset).  A user's
  // Everyday arrangement is preserved in its own slot when they visit
  // Agriculture, and switching back restores it.  No layout is ever
  // clobbered by a persona switch — each persona has an independent
  // slot.  Also exits edit mode so a persona click during arrangement
  // ends the arrangement session cleanly.
  useEffect(() => {
    setLayoutState((cur) => {
      const next = loadLayoutForPersona(persona);
      return JSON.stringify(cur) !== JSON.stringify(next) ? next : cur;
    });
    setEditMode(false);
  }, [persona]);

  // Reconcile with backend on mount.  Wait for syncUIPrefs's
  // backend-wins pass to land any backend-stored per-persona slot
  // (and any backend-stored legacy key) into localStorage, then run
  // the legacy migration a SECOND time so a customization that only
  // lived in backend gets moved into its persona-specific slot, and
  // finally reload the CURRENT persona's layout.  The useState-init
  // migration only catches local-only legacy; this one catches the
  // backend-only path.  Migration is idempotent.
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      migrateLegacyLayoutOnce();
      const syncedPersona = prefs[PERSONA_PREF_KEY] ?? persona;
      const next = loadLayoutForPersona(syncedPersona);
      setLayoutState((cur) =>
        JSON.stringify(cur) !== JSON.stringify(next) ? next : cur,
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <DashboardLayoutContext.Provider
      value={{
        layout,
        editMode,
        setEditMode,
        reorderTiles,
        addTile,
        removeTile,
        setTileColSpan,
        setAllTilesSpan,
        setTileWindDisplay,
        resetToDefault,
      }}
    >
      {children}
    </DashboardLayoutContext.Provider>
  );
}

// --- Hook ---

export function useDashboardLayout(): DashboardLayoutContextValue {
  const ctx = useContext(DashboardLayoutContext);
  if (!ctx) {
    throw new Error(
      "useDashboardLayout must be used within a DashboardLayoutProvider",
    );
  }
  return ctx;
}

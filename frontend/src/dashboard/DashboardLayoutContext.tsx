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
} from "./tileRegistry.ts";
import { readUIPref, writeUIPref, syncUIPrefs } from "../utils/uiPrefs.ts";
import { usePersona, DEFAULT_PERSONA } from "../context/PersonaContext.tsx";

const PERSONA_PREF_KEY = "ui_persona";

function readCurrentPersonaFromStorage(): string {
  // Synchronous read for the initial layout — matches how ThemeContext
  // resolves themeName before the React tree mounts (context reads only
  // work inside components, but the initial useState computation is
  // outside the component during first render's setup).
  return readUIPref(PERSONA_PREF_KEY, DEFAULT_PERSONA);
}

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

const PREF_KEY = "ui_dashboard_layout";
const OLD_COLUMNS_KEY = "davis-wx-dashboard-columns";

function migrateV1(parsed: { version: number; tiles: { tileId: string; colSpan?: number }[] }): DashboardLayout {
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
  saveLayout(migrated);
  return migrated;
}

function parseLayout(raw: string, fallback: DashboardLayout): DashboardLayout {
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw) as DashboardLayout;

    // Migrate v1 layouts
    if (parsed.version === 1) {
      return migrateV1(parsed);
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

function loadLayout(): DashboardLayout {
  // The persona chosen at page-load time picks the first-visit default.
  // A saved layout in localStorage still wins — parseLayout only falls
  // back to the persona default when the stored value is empty or
  // corrupt.  Users who arrived with a saved layout keep it exactly.
  const personaDefault = getPersonaDefaultLayout(readCurrentPersonaFromStorage());
  return parseLayout(readUIPref(PREF_KEY, ""), personaDefault);
}

/**
 * True when the browser's localStorage carries a valid, current-schema
 * saved layout at the moment this call runs.  Called once during the
 * useState lazy initializer so the answer is captured BEFORE
 * syncUIPrefs() overwrites localStorage with backend-reconciled values
 * (see uiPrefs.ts `_doSync`, the "backend wins" pass).  Without this
 * pre-capture, an anonymous user whose \`writeUIPref\` PUT was 401/403'd
 * would look indistinguishable from a fresh visitor after sync, and
 * the mount-time reconcile would clobber their local-only saved
 * arrangement.
 */
function hasLocalSavedLayout(): boolean {
  const raw = readUIPref(PREF_KEY, "");
  if (!raw) return false;
  try {
    const p = JSON.parse(raw);
    if (p.version === 1) return true;
    if (p.version !== LAYOUT_VERSION) return false;
    return Array.isArray(p.tiles) && p.tiles.some(
      (t: { tileId: string }) => t.tileId in TILE_REGISTRY,
    );
  } catch {
    return false;
  }
}

function saveLayout(layout: DashboardLayout): void {
  writeUIPref(PREF_KEY, JSON.stringify(layout));
}

// --- Provider ---

export function DashboardLayoutProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [layout, setLayoutState] = useState<DashboardLayout>(loadLayout);
  const [editMode, setEditMode] = useState(false);
  // Capture whether the browser had a valid local saved layout at
  // render time (before syncUIPrefs's clobber pass); used below to
  // avoid resetting a local-only saved arrangement when the backend
  // has no dashboard layout of its own.
  const [initialHadSavedLayout] = useState<boolean>(hasLocalSavedLayout);
  const { persona } = usePersona();

  const updateLayout = useCallback((next: DashboardLayout) => {
    setLayoutState(next);
    saveLayout(next);
  }, []);

  const reorderTiles = useCallback(
    (fromIndex: number, toIndex: number) => {
      setLayoutState((prev) => {
        const tiles = [...prev.tiles];
        const [moved] = tiles.splice(fromIndex, 1);
        tiles.splice(toIndex, 0, moved);
        const next = { ...prev, tiles };
        saveLayout(next);
        return next;
      });
    },
    [],
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
        saveLayout(next);
        return next;
      });
    },
    [],
  );

  const removeTile = useCallback((tileId: string) => {
    setLayoutState((prev) => {
      const next = {
        ...prev,
        tiles: prev.tiles.filter((t) => t.tileId !== tileId),
      };
      saveLayout(next);
      return next;
    });
  }, []);

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
        saveLayout(next);
        return next;
      });
    },
    [],
  );

  const setAllTilesSpan = useCallback((colSpan: number) => {
    setLayoutState((prev) => {
      const next = {
        ...prev,
        tiles: prev.tiles.map((t) => {
          const def = TILE_REGISTRY[t.tileId];
          const min = def?.minColSpan ?? 2;
          return { ...t, colSpan: Math.max(min, Math.min(GRID_COLUMNS, colSpan)) };
        }),
      };
      saveLayout(next);
      return next;
    });
  }, []);

  const setTileWindDisplay = useCallback((tileId: string, mode: "compass" | "rose") => {
    setLayoutState((prev) => {
      const next = {
        ...prev,
        tiles: prev.tiles.map((t) =>
          t.tileId === tileId ? { ...t, windDisplay: mode === "compass" ? undefined : mode } : t,
        ),
      };
      saveLayout(next);
      return next;
    });
  }, []);

  const resetToDefault = useCallback(() => {
    // Reset to the CURRENT persona's default, not the frozen
    // pre-persona all-tiles default.  A user on Agriculture who hits
    // "Reset" expects the agricultural tile set, not the nerd shape.
    updateLayout(getPersonaDefaultLayout(persona));
    setEditMode(false);
  }, [updateLayout, persona]);

  // Reconcile with backend on mount.  Three cases, all fed by the same
  // syncUIPrefs() promise so backend prefs land once and get used
  // consistently:
  //
  //   1. Backend has a saved layout — it always wins over local.
  //      parseLayout falls back to the persona default only if the
  //      stored value is corrupt.
  //
  //   2. Backend has none but browser does — keep the local layout.
  //      This is the anonymous-user path where writeUIPref's backend
  //      PUT was 401/403'd; localStorage retained the user's own
  //      arrangement and we must not clobber it just because backend
  //      is empty.  `initialHadSavedLayout` was captured before
  //      syncUIPrefs's "backend wins" clobber overwrote localStorage.
  //
  //   3. Nothing anywhere — seed from the backend-synced persona so a
  //      fresh browser whose local `ui_persona` is still the default
  //      but whose backend `ui_persona` is agriculture (set on another
  //      device or by the setup wizard) lands on the agricultural
  //      default rather than the local-persona everyday default.
  //
  // The effect intentionally does not depend on `persona`; a persona
  // switch after mount MUST NOT reseat a saved layout.  The synced
  // persona used below comes from the backend prefs snapshot, not
  // from the live context value.
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const raw = prefs[PREF_KEY];
      const syncedPersona = prefs[PERSONA_PREF_KEY] ?? persona;
      const personaDefault = getPersonaDefaultLayout(syncedPersona);
      let next: DashboardLayout;
      if (raw) {
        next = parseLayout(raw, personaDefault);
      } else if (initialHadSavedLayout) {
        return;
      } else {
        next = personaDefault;
      }
      setLayoutState((cur) => {
        if (JSON.stringify(cur) !== JSON.stringify(next)) return next;
        return cur;
      });
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

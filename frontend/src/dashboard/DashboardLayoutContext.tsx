/**
 * Dashboard layout context — manages tile arrangement with backend-persisted
 * preferences (localStorage as sync cache). Follows the same pattern as
 * ThemeContext and WeatherBackgroundContext.
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
  DEFAULT_LAYOUT,
  LAYOUT_VERSION,
  GRID_COLUMNS,
} from "./tileRegistry.ts";
import { readUIPref, writeUIPref, syncUIPrefs } from "../utils/uiPrefs.ts";

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

function parseLayout(raw: string): DashboardLayout {
  if (!raw) return DEFAULT_LAYOUT;
  try {
    const parsed = JSON.parse(raw) as DashboardLayout;

    // Migrate v1 layouts
    if (parsed.version === 1) {
      return migrateV1(parsed);
    }

    // Version check — fall back to default if schema changed
    if (parsed.version !== LAYOUT_VERSION) return DEFAULT_LAYOUT;

    // Validate: strip tiles with unknown IDs
    const validTiles = parsed.tiles.filter(
      (t) => t.tileId in TILE_REGISTRY,
    );
    if (validTiles.length === 0) return DEFAULT_LAYOUT;

    return { version: LAYOUT_VERSION, tiles: validTiles };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function loadLayout(): DashboardLayout {
  return parseLayout(readUIPref(PREF_KEY, ""));
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

  const resetToDefault = useCallback(() => {
    updateLayout(DEFAULT_LAYOUT);
    setEditMode(false);
  }, [updateLayout]);

  // Reconcile with backend on mount
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const raw = prefs[PREF_KEY];
      if (raw) {
        const synced = parseLayout(raw);
        setLayoutState((cur) => {
          if (JSON.stringify(cur) !== JSON.stringify(synced)) return synced;
          return cur;
        });
      }
    });
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

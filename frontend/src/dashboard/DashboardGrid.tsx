/**
 * Dashboard grid container. Renders tiles from the layout context.
 * Uses a 12-column CSS grid. Each tile spans 2-12 columns and can be
 * drag-resized in edit mode.
 * Normal mode: plain CSS grid, zero DnD overhead.
 * Edit mode: DndContext + SortableContext for drag-and-drop reordering,
 *   plus per-tile ResizeHandle for width adjustment.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  TouchSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  rectSortingStrategy,
} from "@dnd-kit/sortable";

import { useDashboardLayout } from "./DashboardLayoutContext.tsx";
import { CompactProvider } from "./CompactContext.tsx";
import { TILE_REGISTRY, GRID_COLUMNS, DEFAULT_COL_SPAN, GAP } from "./tileRegistry.ts";
import TileRenderer from "./TileRenderer.tsx";
import SortableTile from "./SortableTile.tsx";
import TileCatalogModal from "./TileCatalogModal.tsx";
import FlipTile from "../components/common/FlipTile.tsx";
import TrendModal from "../components/common/TrendModal.tsx";
import NowcastBanner from "../components/panels/NowcastBanner.tsx";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import { useIsMobile } from "../hooks/useIsMobile.ts";
import { useFeatureFlags } from "../context/FeatureFlagsContext.tsx";

const COMPACT_THRESHOLD = 240;

const editToggleStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid var(--color-border)",
  borderRadius: 6,
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: 14,
  color: "var(--color-text-secondary)",
  fontFamily: "var(--font-body)",
  marginLeft: 12,
  verticalAlign: "middle",
};

const toolbarStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  marginBottom: 12,
  padding: "8px 12px",
  background: "var(--color-bg-card)",
  border: "1px solid var(--color-accent)",
  borderRadius: 8,
  fontSize: 14,
  fontFamily: "var(--font-body)",
  flexWrap: "wrap",
};

const toolbarBtnStyle: React.CSSProperties = {
  padding: "6px 16px",
  borderRadius: 6,
  border: "none",
  cursor: "pointer",
  fontSize: 13,
  fontFamily: "var(--font-body)",
  fontWeight: 600,
};

const addTilePlaceholderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  minHeight: 160,
  border: "2px dashed var(--color-border)",
  borderRadius: "var(--gauge-border-radius, 16px)",
  color: "var(--color-text-muted)",
  fontSize: 16,
  fontFamily: "var(--font-body)",
  cursor: "pointer",
  transition: "border-color 0.2s, color 0.2s",
  gridColumn: "span 2",
};

const PRESETS = [
  { label: "6/row", span: 2 },
  { label: "4/row", span: 3 },
  { label: "3/row", span: 4 },
  { label: "2/row", span: 6 },
] as const;

function LayoutPresets({ onPreset }: { onPreset: (span: number) => void }) {
  return (
    <span style={{ display: "inline-flex", gap: 0, verticalAlign: "middle" }}>
      {PRESETS.map(({ label, span }, i) => (
        <button
          key={span}
          onClick={() => onPreset(span)}
          title={`Set all tiles to ${label}`}
          style={{
            width: 42,
            height: 28,
            border: "1px solid var(--color-border)",
            borderRight: i < PRESETS.length - 1 ? "none" : "1px solid var(--color-border)",
            borderRadius: i === 0 ? "6px 0 0 6px" : i === PRESETS.length - 1 ? "0 6px 6px 0" : 0,
            background: "none",
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            fontSize: 11,
            fontWeight: 600,
            fontFamily: "var(--font-body)",
            padding: 0,
            lineHeight: 1,
          }}
        >
          {label}
        </button>
      ))}
    </span>
  );
}

/** Compute the pixel width of a tile given its span and the grid width. */
function tilePixelWidth(span: number, gridW: number): number {
  if (gridW <= 0) return 999;
  const cellWidth = (gridW - (GRID_COLUMNS - 1) * GAP) / GRID_COLUMNS;
  return span * cellWidth + (span - 1) * GAP;
}

export default function DashboardGrid() {
  const {
    layout,
    editMode,
    setEditMode,
    reorderTiles,
    removeTile,
    setTileColSpan,
    setAllTilesSpan,
    resetToDefault,
  } = useDashboardLayout();
  const { currentConditions } = useWeatherData();
  const { flags } = useFeatureFlags();
  const isMobile = useIsMobile();
  const [showCatalog, setShowCatalog] = useState(false);
  const [gridWidth, setGridWidth] = useState(0);
  const gridRef = useRef<HTMLDivElement>(null);

  // Observe grid width for compact detection and resize handle math
  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setGridWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: `repeat(${GRID_COLUMNS}, 1fr)`,
    gap: `${GAP}px`,
  };

  const hasSolar =
    currentConditions?.solar_radiation != null ||
    currentConditions?.uv_index != null;

  // DnD sensors — only used in edit mode
  const pointerSensor = useSensor(PointerSensor, {
    activationConstraint: { distance: 8 },
  });
  const touchSensor = useSensor(TouchSensor, {
    activationConstraint: { delay: 250, tolerance: 5 },
  });
  const keyboardSensor = useSensor(KeyboardSensor);
  const sensors = useSensors(pointerSensor, touchSensor, keyboardSensor);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = layout.tiles.findIndex(
        (t) => t.tileId === active.id,
      );
      const newIndex = layout.tiles.findIndex(
        (t) => t.tileId === over.id,
      );
      if (oldIndex !== -1 && newIndex !== -1) {
        reorderTiles(oldIndex, newIndex);
      }
    },
    [layout.tiles, reorderTiles],
  );

  const tileIds = layout.tiles.map((t) => t.tileId);

  /** Compute effective span for a tile (mobile override). */
  const effectiveSpan = (rawSpan: number, minSpan: number): number => {
    if (isMobile) return Math.max(6, minSpan);
    return Math.min(rawSpan, GRID_COLUMNS);
  };

  // --- Normal mode: plain grid, no DnD ---
  if (!editMode) {
    return (
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
        <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
          <h2
            className="dashboard-heading"
            style={{
              margin: "0 0 16px 0",
              fontSize: "24px",
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
              whiteSpace: "nowrap",
            }}
          >
            Current Conditions
            <button
              style={editToggleStyle}
              onClick={() => setEditMode(true)}
              aria-label="Edit dashboard layout"
              title="Edit dashboard layout"
            >
              {"\u270E"}
            </button>
          </h2>
        </div>

        <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
        {flags.nowcastEnabled && <NowcastBanner />}

        <div ref={gridRef} className="dashboard-grid" style={gridStyle}>
          {layout.tiles.map((placement) => {
            const def = TILE_REGISTRY[placement.tileId];
            if (!def) return null;
            const rawSpan = placement.colSpan ?? DEFAULT_COL_SPAN;
            const span = effectiveSpan(rawSpan, def.minColSpan);
            const tileW = tilePixelWidth(span, gridWidth);
            const compact = isMobile || tileW < COMPACT_THRESHOLD;

            const content = <TileRenderer tileId={placement.tileId} />;
            const wrapped = def.hasFlipTile ? (
              compact ? (
                <TrendModal
                  sensor={def.sensor!}
                  label={def.chartLabel!}
                  unit={def.chartUnit!}
                >
                  {content}
                </TrendModal>
              ) : (
                <FlipTile
                  sensor={def.sensor!}
                  label={def.chartLabel!}
                  unit={def.chartUnit!}
                >
                  {content}
                </FlipTile>
              )
            ) : (
              content
            );

            return (
              <div
                key={placement.tileId}
                style={{
                  gridColumn: `span ${span}`,
                }}
              >
                <CompactProvider value={compact}>
                  {wrapped}
                </CompactProvider>
              </div>
            );
          })}
        </div>
        </div>
      </div>
    );
  }

  // --- Edit mode: DnD grid ---
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
        <h2
          style={{
            margin: "0 0 16px 0",
            fontSize: "24px",
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Current Conditions
        </h2>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
      <NowcastBanner />

      {/* Edit toolbar */}
      <div className="dashboard-toolbar" style={toolbarStyle}>
        <span style={{ color: "var(--color-accent)", fontWeight: 600 }}>
          Editing Layout
        </span>
        {!isMobile && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 13, color: "var(--color-text-secondary)" }}>Presets</span>
            <LayoutPresets onPreset={setAllTilesSpan} />
          </span>
        )}
        <span style={{ flex: 1 }} />
        <button
          style={{
            ...toolbarBtnStyle,
            background: "var(--color-bg-secondary)",
            color: "var(--color-text)",
            border: "1px solid var(--color-border)",
          }}
          onClick={resetToDefault}
        >
          Reset to Default
        </button>
        <button
          style={{
            ...toolbarBtnStyle,
            background: "var(--color-accent)",
            color: "#fff",
          }}
          onClick={() => setEditMode(false)}
        >
          Done
        </button>
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={tileIds}
          strategy={rectSortingStrategy}
        >
          <div ref={gridRef} className="dashboard-grid" style={gridStyle}>
            {layout.tiles.map((placement) => {
              const def = TILE_REGISTRY[placement.tileId];
              if (!def) return null;
              const rawSpan = placement.colSpan ?? DEFAULT_COL_SPAN;
              const span = effectiveSpan(rawSpan, def.minColSpan);
              const tileW = tilePixelWidth(span, gridWidth);
              const compact = isMobile || tileW < COMPACT_THRESHOLD;

              const content = <TileRenderer tileId={placement.tileId} />;
              const wrapped = (!compact && def.hasFlipTile) ? (
                <FlipTile
                  sensor={def.sensor!}
                  label={def.chartLabel!}
                  unit={def.chartUnit!}
                  disabled
                >
                  {content}
                </FlipTile>
              ) : (
                content
              );

              return (
                <SortableTile
                  key={placement.tileId}
                  id={placement.tileId}
                  colSpan={span}
                  minSpan={def.minColSpan}
                  gridWidth={gridWidth}
                  onRemove={() => removeTile(placement.tileId)}
                  onSetSpan={(n) => setTileColSpan(placement.tileId, n)}
                >
                  <CompactProvider value={compact}>
                    {wrapped}
                  </CompactProvider>
                </SortableTile>
              );
            })}

            {/* Add tile placeholder */}
            <div
              style={addTilePlaceholderStyle}
              onClick={() => setShowCatalog(true)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") setShowCatalog(true);
              }}
            >
              + Add Tile
            </div>
          </div>
        </SortableContext>
      </DndContext>

      {showCatalog && (
        <TileCatalogModal
          currentTileIds={tileIds}
          hasSolar={hasSolar}
          onClose={() => setShowCatalog(false)}
        />
      )}
      </div>
    </div>
  );
}

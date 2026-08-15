/**
 * Dashboard grid container. Renders tiles from the layout context.
 * Uses a 12-column CSS grid. Each tile spans 2-12 columns and can be
 * drag-resized in edit mode.
 * Normal mode: plain CSS grid, zero DnD overhead.
 * Edit mode: DndContext + SortableContext for drag-and-drop reordering,
 *   per-tile ResizeHandle for width adjustment, and wind display toggle
 *   (compass ↔ rose).
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
import { TILE_REGISTRY, GRID_COLUMNS, DEFAULT_COL_SPAN, DEFAULT_ROW_SPAN, GRID_ROW_UNIT_PX, GAP } from "./tileRegistry.ts";
import TileRenderer from "./TileRenderer.tsx";
import SortableTile from "./SortableTile.tsx";
import TileCatalogModal from "./TileCatalogModal.tsx";
import FlipTile from "../components/common/FlipTile.tsx";
import TrendModal from "../components/common/TrendModal.tsx";
import WindHistory from "../components/charts/WindHistory.tsx";
import NowcastBanner from "../components/panels/NowcastBanner.tsx";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import { useIsMobile } from "../hooks/useIsMobile.ts";
import { useFeatureFlags } from "../context/FeatureFlagsContext.tsx";

const COMPACT_THRESHOLD = 240;

const editToggleStyle: React.CSSProperties = {
  background: "var(--color-bg-card-solid, var(--color-bg-card))",
  border: "1px solid var(--color-text-secondary)",
  borderRadius: 6,
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: "calc(16px * var(--font-scale))",
  color: "var(--color-text)",
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
  fontSize: "calc(14px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  flexWrap: "wrap",
};

const toolbarBtnStyle: React.CSSProperties = {
  padding: "6px 16px",
  borderRadius: 6,
  border: "none",
  cursor: "pointer",
  fontSize: "calc(13px * var(--font-scale))",
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
  fontSize: "calc(16px * var(--font-scale))",
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
            fontSize: "calc(11px * var(--font-scale))",
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
    setTileWindDisplay,
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
    // GRID_ROW_UNIT_PX per row.  Each TilePlacement declares
    // ``rowSpan: N`` for an N×unit-tall cell.  Cells with no
    // explicit rowSpan get DEFAULT_ROW_SPAN.  Small unit + span
    // is what lets a 300px dial sit beside a short 4-row table
    // without the table stretching to match the dial.
    gridAutoRows: `${GRID_ROW_UNIT_PX}px`,
    // rowGap: 0 so a tile with ``rowSpan: 26`` is 208 px — not
    // 26×8 + 25×16.  The tile-wrapper's ``paddingBottom: GAP``
    // (border-box) carves the visible vertical gutter out of the
    // top of each cell instead of stacking gap between every 8-px
    // row line.  columnGap keeps horizontal spacing per Design's
    // ``rowGap: 0, columnGap: GAP`` fix in REVIEW-03.
    columnGap: `${GAP}px`,
    rowGap: 0,
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
        <div style={{ flexShrink: 0, padding: isMobile ? "4px 12px 0" : "4px 24px 0" }}>
          <h2
            className="dashboard-heading"
            style={{
              margin: "0 0 16px 0",
              fontSize: "calc(24px * var(--font-scale))",
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

        <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: isMobile ? "0 12px 12px" : "0 24px 24px" }}>
        {flags.nowcastEnabled && <NowcastBanner />}

        <div ref={gridRef} className="dashboard-grid" style={gridStyle}>
          {layout.tiles.map((placement) => {
            const def = TILE_REGISTRY[placement.tileId];
            if (!def) return null;
            const rawSpan = placement.colSpan ?? DEFAULT_COL_SPAN;
            const span = effectiveSpan(rawSpan, def.minColSpan);
            const tileW = tilePixelWidth(span, gridWidth);
            const compact = isMobile || tileW < COMPACT_THRESHOLD;

            const content = <TileRenderer tileId={placement.tileId} windDisplay={placement.windDisplay} />;
            const windBack = placement.tileId === "wind" ? <WindHistory hours={4} /> : undefined;
            const wrapped = def.hasFlipTile ? (
              compact ? (
                <TrendModal
                  sensor={def.sensor!}
                  label={def.chartLabel!}
                  unit={def.chartUnit!}
                  backContent={windBack}
                >
                  {content}
                </TrendModal>
              ) : (
                <FlipTile
                  sensor={def.sensor!}
                  label={def.chartLabel!}
                  unit={def.chartUnit!}
                  backContent={windBack}
                >
                  {content}
                </FlipTile>
              )
            ) : (
              content
            );

            const rowSpan = placement.rowSpan ?? DEFAULT_ROW_SPAN;
            const useExplicit = !isMobile && placement.gridColStart != null && placement.gridRowStart != null;
            return (
              <div
                key={placement.tileId}
                style={{
                  gridColumn: useExplicit
                    ? `${placement.gridColStart} / span ${span}`
                    : `span ${span}`,
                  gridRow: useExplicit
                    ? `${placement.gridRowStart} / span ${rowSpan}`
                    : `span ${rowSpan}`,
                  paddingBottom: GAP,
                  boxSizing: "border-box",
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
      <div style={{ flexShrink: 0, padding: isMobile ? "4px 12px 0" : "4px 24px 0" }}>
        <h2
          style={{
            margin: "0 0 16px 0",
            fontSize: "calc(24px * var(--font-scale))",
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Current Conditions
        </h2>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: isMobile ? "0 12px 12px" : "0 24px 24px" }}>
      <NowcastBanner />

      {/* Edit toolbar */}
      <div className="dashboard-toolbar" style={toolbarStyle}>
        <span style={{ color: "var(--color-accent)", fontWeight: 600 }}>
          Editing Layout
        </span>
        {!isMobile && (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: "calc(13px * var(--font-scale))", color: "var(--color-text-secondary)" }}>Presets</span>
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

              const content = <TileRenderer tileId={placement.tileId} windDisplay={placement.windDisplay} />;
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
                  rowSpan={placement.rowSpan ?? DEFAULT_ROW_SPAN}
                  minSpan={def.minColSpan}
                  gridWidth={gridWidth}
                  onRemove={() => removeTile(placement.tileId)}
                  onSetSpan={(n) => setTileColSpan(placement.tileId, n)}
                  isWind={placement.tileId === "wind"}
                  windDisplay={placement.windDisplay ?? "compass"}
                  onToggleWindDisplay={() => setTileWindDisplay(
                    placement.tileId,
                    (placement.windDisplay ?? "compass") === "compass" ? "rose" : "compass",
                  )}
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

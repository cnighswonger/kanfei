/**
 * Drag-resize handle for dashboard tiles in edit mode.
 * Renders a vertical bar on the tile's right edge. Dragging it
 * horizontally snaps to the 12-column grid boundaries.
 */

import { useCallback, useRef } from "react";
import { GRID_COLUMNS, GAP } from "./tileRegistry.ts";

interface ResizeHandleProps {
  currentSpan: number;
  minSpan: number;
  gridWidth: number;
  onSpanChange: (newSpan: number) => void;
}

export default function ResizeHandle({
  currentSpan,
  minSpan,
  gridWidth,
  onSpanChange,
}: ResizeHandleProps) {
  const dragRef = useRef<{ startX: number; startSpan: number } | null>(null);
  const lastSpanRef = useRef(currentSpan);
  lastSpanRef.current = currentSpan;

  const cellWidth = (gridWidth - (GRID_COLUMNS - 1) * GAP) / GRID_COLUMNS;
  const colStep = cellWidth + GAP;

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragRef.current = { startX: e.clientX, startSpan: lastSpanRef.current };
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onPointerMove = (ev: PointerEvent) => {
        if (!dragRef.current) return;
        const dx = ev.clientX - dragRef.current.startX;
        const deltaSpan = Math.round(dx / colStep);
        const newSpan = Math.max(
          minSpan,
          Math.min(GRID_COLUMNS, dragRef.current.startSpan + deltaSpan),
        );
        if (newSpan !== lastSpanRef.current) {
          onSpanChange(newSpan);
        }
      };

      const onPointerUp = () => {
        dragRef.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        document.removeEventListener("pointermove", onPointerMove);
        document.removeEventListener("pointerup", onPointerUp);
      };

      document.addEventListener("pointermove", onPointerMove);
      document.addEventListener("pointerup", onPointerUp);
    },
    [colStep, minSpan, onSpanChange],
  );

  return (
    <div
      onPointerDown={onPointerDown}
      style={{
        position: "absolute",
        right: -4,
        top: "10%",
        bottom: "10%",
        width: 8,
        cursor: "col-resize",
        zIndex: 15,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        touchAction: "none",
      }}
    >
      {/* Visual grip bar */}
      <div
        style={{
          width: 4,
          height: "40%",
          minHeight: 20,
          borderRadius: 2,
          background: "var(--color-accent)",
          opacity: 0.5,
          transition: "opacity 0.15s",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.opacity = "1";
        }}
        onMouseLeave={(e) => {
          if (!dragRef.current) {
            (e.currentTarget as HTMLElement).style.opacity = "0.5";
          }
        }}
      />
    </div>
  );
}

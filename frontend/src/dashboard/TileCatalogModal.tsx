/**
 * Modal overlay for adding tiles to the dashboard.
 * Shows all available tiles grouped by category.
 */

import { useDashboardLayout } from "./DashboardLayoutContext.tsx";
import { TILE_REGISTRY, type TileDefinition } from "./tileRegistry.ts";

interface TileCatalogModalProps {
  currentTileIds: string[];
  hasSolar: boolean;
  onClose: () => void;
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0, 0, 0, 0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 200,
};

const modalStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--gauge-border-radius, 16px)",
  padding: "24px",
  maxWidth: 520,
  width: "90vw",
  maxHeight: "80vh",
  overflowY: "auto",
  boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
};

const categoryOrder = [
  "temperature",
  "atmosphere",
  "wind",
  "rain",
  "solar",
  "status",
] as const;

const categoryLabels: Record<string, string> = {
  temperature: "Temperature",
  atmosphere: "Atmosphere",
  wind: "Wind",
  rain: "Rain",
  solar: "Solar",
  status: "Status",
};

export default function TileCatalogModal({
  currentTileIds,
  hasSolar,
  onClose,
}: TileCatalogModalProps) {
  const { addTile } = useDashboardLayout();

  // Group tiles by category
  const allTiles = Object.values(TILE_REGISTRY);
  const grouped = new Map<string, TileDefinition[]>();
  for (const cat of categoryOrder) {
    const tiles = allTiles.filter((t) => t.category === cat);
    if (tiles.length > 0) grouped.set(cat, tiles);
  }

  const handleAdd = (tileId: string) => {
    addTile(tileId);
    onClose();
  };

  return (
    <div
      style={overlayStyle}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div style={modalStyle}>
        <h3
          style={{
            margin: "0 0 16px 0",
            fontSize: 18,
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Add Tile
        </h3>

        {[...grouped.entries()].map(([cat, tiles]) => (
          <div key={cat} style={{ marginBottom: 16 }}>
            <div
              style={{
                fontSize: 12,
                fontFamily: "var(--font-body)",
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                marginBottom: 8,
              }}
            >
              {categoryLabels[cat] ?? cat}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: 8,
              }}
            >
              {tiles.map((tile) => {
                const isPresent = currentTileIds.includes(tile.id);
                const needsSolar = tile.requiresSolar && !hasSolar;
                const disabled = isPresent || needsSolar;

                return (
                  <button
                    key={tile.id}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 8,
                      border: "1px solid var(--color-border)",
                      background: disabled
                        ? "var(--color-bg-secondary)"
                        : "var(--color-bg-card)",
                      color: disabled
                        ? "var(--color-text-muted)"
                        : "var(--color-text)",
                      fontSize: 13,
                      fontFamily: "var(--font-body)",
                      cursor: disabled ? "default" : "pointer",
                      opacity: disabled ? 0.5 : 1,
                      textAlign: "left",
                      transition: "background 0.15s",
                    }}
                    disabled={disabled}
                    onClick={() => !disabled && handleAdd(tile.id)}
                    title={
                      isPresent
                        ? "Already on dashboard"
                        : needsSolar
                          ? "Requires solar sensor"
                          : `Add ${tile.label}`
                    }
                  >
                    {isPresent ? "\u2713 " : ""}
                    {tile.label}
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 16 }}>
          <button
            style={{
              padding: "8px 20px",
              borderRadius: 6,
              border: "none",
              background: "var(--color-accent)",
              color: "#fff",
              fontSize: 14,
              fontFamily: "var(--font-body)",
              fontWeight: 600,
              cursor: "pointer",
            }}
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Wrapper that gives any gauge tile a click-to-flip behaviour.
 * Front: the gauge (children). Back: a 1-hour sparkline chart.
 *
 * Note: the /api/history endpoint returns display-ready values
 * (already converted from raw DB units), so no client-side
 * transformation is needed here.
 */
import { useState, useCallback, type ReactNode } from "react";
import { fetchHistory } from "../../api/client.ts";
import TrendChart from "../charts/TrendChart.tsx";

// --- Component ---

interface FlipTileProps {
  /** Sensor key for the history API (e.g. "outside_temp"). */
  sensor: string;
  /** Title shown on the chart face. */
  label: string;
  /** Display unit for chart tooltip (e.g. "°F"). */
  unit: string;
  /** When true, click does not flip (used during dashboard edit mode). */
  disabled?: boolean;
  children: ReactNode;
}

export default function FlipTile({
  sensor,
  label,
  unit,
  disabled,
  children,
}: FlipTileProps) {
  const [flipped, setFlipped] = useState(false);
  const [chartData, setChartData] = useState<{ x: number; y: number }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleClick = useCallback(() => {
    if (disabled) return;
    const nextFlipped = !flipped;
    setFlipped(nextFlipped);

    if (nextFlipped) {
      // Fetch last hour of data each time we flip to back
      setLoading(true);
      const now = new Date();
      const hourAgo = new Date(now.getTime() - 3_600_000);
      fetchHistory(sensor, hourAgo.toISOString(), now.toISOString(), "raw")
        .then((res) => {
          const pts = res.points
            .map((p) => ({ x: new Date(p.timestamp).getTime(), y: p.value }))
            .filter((pt): pt is { x: number; y: number } => Number.isFinite(pt.x) && Number.isFinite(pt.y));
          setChartData(pts);
        })
        .catch(() => setChartData([]))
        .finally(() => setLoading(false));
    }
  }, [flipped, disabled, sensor]);

  return (
    <div
      style={{ perspective: "1000px", cursor: "pointer", height: "100%" }}
      onClick={handleClick}
    >
      <div
        style={{
          transition: "transform 0.6s ease",
          transformStyle: "preserve-3d",
          transform: flipped ? "rotateY(180deg)" : "none",
          position: "relative",
          height: "100%",
        }}
      >
        {/* Front face — the gauge */}
        <div style={{ backfaceVisibility: "hidden", height: "100%" }}>
          {children}
        </div>

        {/* Back face — the chart */}
        <div
          style={{
            backfaceVisibility: "hidden",
            transform: "rotateY(180deg)",
            position: "absolute",
            inset: 0,
            background: "var(--color-bg-card-solid, var(--color-bg-card))",
            borderRadius: "var(--gauge-border-radius, 16px)",
            border: "1px solid var(--color-border)",
            boxShadow: "var(--gauge-shadow)",
            padding: "12px",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <h4
            style={{
              margin: "0 0 4px 0",
              fontSize: "14px",
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            {label} — Past Hour
          </h4>

          {loading ? (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-text-muted)",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
              }}
            >
              Loading...
            </div>
          ) : chartData.length > 0 ? (
            <div style={{ flex: 1, minHeight: 0 }}>
              <TrendChart title="" data={chartData} unit={unit} sensor={sensor} />
            </div>
          ) : (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--color-text-muted)",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
              }}
            >
              No data available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

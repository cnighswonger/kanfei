/**
 * Wrapper that gives any gauge tile a click-to-flip behaviour.
 * Front: the gauge (children). Back: a 1-hour sparkline chart.
 *
 * Transparency: the hidden wrapper gets an opaque background to prevent
 * bleed-through during the 3D transform. The visible wrapper is transparent
 * — content inside provides its own card styling.
 */
import { useState, useCallback, type ReactNode } from "react";
import { fetchHistory } from "../../api/client.ts";
import TrendChart from "../charts/TrendChart.tsx";

// --- Component ---

interface FlipTileProps {
  sensor: string;
  label: string;
  unit: string;
  disabled?: boolean;
  backContent?: ReactNode;
  defaultFlipped?: boolean;
  children: ReactNode;
}

export default function FlipTile({
  sensor,
  label,
  unit,
  disabled,
  backContent,
  defaultFlipped,
  children,
}: FlipTileProps) {
  const [toggled, setToggled] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [chartData, setChartData] = useState<{ x: number; y: number }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleClick = useCallback(() => {
    if (disabled) return;
    const nextToggled = !toggled;
    setToggled(nextToggled);
    setAnimating(true);
    setTimeout(() => setAnimating(false), 650);

    const willShowChart = defaultFlipped ? !nextToggled : nextToggled;
    if (willShowChart && !backContent) {
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
  }, [toggled, disabled, sensor, backContent, defaultFlipped]);

  // --- Chart face content (has its own card styling) ---
  const chartFace = (
    <div
      style={{
        height: "100%",
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        border: "1px solid var(--color-border)",
        boxShadow: "var(--gauge-shadow)",
        padding: "12px",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        boxSizing: "border-box",
      }}
    >
      {backContent ? (
        <div style={{ flex: 1, minHeight: 0 }}>{backContent}</div>
      ) : (
        <>
          <h4 style={{ margin: "0 0 4px 0", fontSize: "14px", fontFamily: "var(--font-heading)", color: "var(--color-text)" }}>
            {label} — Past Hour
          </h4>
          {loading ? (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-text-muted)", fontSize: "13px", fontFamily: "var(--font-body)" }}>Loading...</div>
          ) : chartData.length > 0 ? (
            <div style={{ flex: 1, minHeight: 0 }}><TrendChart title="" data={chartData} unit={unit} sensor={sensor} /></div>
          ) : (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-text-muted)", fontSize: "13px", fontFamily: "var(--font-body)" }}>No data available</div>
          )}
        </>
      )}
    </div>
  );

  // --- Gauge face content (already has its own card styling from the gauge component) ---
  const gaugeFace = children;

  // Swap DOM order when defaultFlipped so the chart starts as the CSS front.
  const frontContent = defaultFlipped ? chartFace : gaugeFace;
  const backContentNode = defaultFlipped ? gaugeFace : chartFace;

  // The hidden face gets an opaque bg to block bleed-through.
  // The visible face has no wrapper bg — the content provides its own.
  const frontVisible = !toggled;

  return (
    <div
      style={{ perspective: "1000px", cursor: "pointer", height: "100%" }}
      onClick={handleClick}
    >
      <div
        style={{
          transition: "transform 0.6s ease",
          transformStyle: "preserve-3d",
          transform: toggled ? "rotateY(180deg)" : "none",
          position: "relative",
          height: "100%",
        }}
      >
        {/* CSS front face — visible when !toggled */}
        <div
          style={{
            backfaceVisibility: "hidden",
            height: "100%",
            // When settled and hidden, remove from rendering entirely
            // to prevent any compositing bleed-through.
            ...(!frontVisible && !animating ? { visibility: "hidden" as const } : {}),
          }}
        >
          {frontContent}
        </div>

        {/* CSS back face — visible when toggled */}
        <div
          style={{
            backfaceVisibility: "hidden",
            transform: "rotateY(180deg)",
            position: "absolute",
            inset: 0,
            ...(frontVisible && !animating ? { visibility: "hidden" as const } : {}),
          }}
        >
          {backContentNode}
        </div>
      </div>
    </div>
  );
}

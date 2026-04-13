/**
 * Wrapper that gives any gauge tile a click-to-flip behaviour.
 * Front: the gauge (children). Back: a 1-hour sparkline chart.
 *
 * Transparency logic: the two CSS-position wrapper divs carry the
 * background.  Whichever wrapper is currently visible gets the
 * transparent --color-bg-card (matches other tiles).  The hidden
 * wrapper gets the opaque --color-bg-card-solid (prevents bleed-
 * through during the 3D transform).  Backgrounds swap on every flip.
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

const VISIBLE_BG = "var(--color-bg-card)";
const HIDDEN_BG = "var(--color-bg-card-solid, var(--color-bg-card))";

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
  const [chartData, setChartData] = useState<{ x: number; y: number }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleClick = useCallback(() => {
    if (disabled) return;
    const nextToggled = !toggled;
    setToggled(nextToggled);

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

  // --- Chart inner content (no background — wrapper handles it) ---
  const chartInner = backContent ? (
    <div style={{ flex: 1, minHeight: 0 }}>
      {backContent}
    </div>
  ) : (
    <>
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
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-text-muted)", fontSize: "13px", fontFamily: "var(--font-body)" }}>
          Loading...
        </div>
      ) : chartData.length > 0 ? (
        <div style={{ flex: 1, minHeight: 0 }}>
          <TrendChart title="" data={chartData} unit={unit} sensor={sensor} />
        </div>
      ) : (
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-text-muted)", fontSize: "13px", fontFamily: "var(--font-body)" }}>
          No data available
        </div>
      )}
    </>
  );

  // Decide which content goes in the CSS front vs back position.
  // defaultFlipped swaps them so the chart starts visible.
  const frontContent = defaultFlipped ? chartInner : children;
  const backContentNode = defaultFlipped ? children : chartInner;

  // The CSS front is visible when !toggled, hidden when toggled.
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
        {/* CSS front face */}
        <div
          style={{
            backfaceVisibility: "hidden",
            height: "100%",
            background: frontVisible ? VISIBLE_BG : HIDDEN_BG,
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
          {frontContent}
        </div>

        {/* CSS back face */}
        <div
          style={{
            backfaceVisibility: "hidden",
            transform: "rotateY(180deg)",
            position: "absolute",
            inset: 0,
            background: frontVisible ? HIDDEN_BG : VISIBLE_BG,
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
          {backContentNode}
        </div>
      </div>
    </div>
  );
}

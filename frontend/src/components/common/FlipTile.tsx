/**
 * Wrapper that gives any gauge tile a click-to-flip behaviour.
 * Front: the gauge (children). Back: a 1-hour sparkline chart.
 *
 * When defaultFlipped is true, the DOM order is swapped so the chart
 * content occupies the CSS front face. This ensures the initially-
 * visible face uses --color-bg-card (honors theme transparency) and
 * the hidden face uses --color-bg-card-solid (prevents bleed-through).
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
  /** Optional custom back-face content. When provided, replaces the default
   *  TrendChart and the component is responsible for its own data fetching. */
  backContent?: ReactNode;
  /** Start with the back face showing. */
  defaultFlipped?: boolean;
  children: ReactNode;
}

/** Styles for the face that sits in the CSS back position (rotated 180deg). */
const backPositionStyle: React.CSSProperties = {
  backfaceVisibility: "hidden",
  transform: "rotateY(180deg)",
  position: "absolute",
  inset: 0,
};

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

    // Fetch trend data when the default TrendChart becomes visible
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

  // --- The two content blocks ---

  const gaugeContent = (
    <div style={{ height: "100%" }}>
      {children}
    </div>
  );

  // The chart face is in the CSS front position when defaultFlipped.
  // Whether it's currently *visible* depends on toggled state:
  //   defaultFlipped && !toggled → chart is front & visible → transparent
  //   defaultFlipped && toggled  → chart is front & hidden  → opaque
  //   !defaultFlipped && !toggled → chart is back & hidden  → opaque
  //   !defaultFlipped && toggled  → chart is back & visible → transparent
  const chartVisible = defaultFlipped ? !toggled : toggled;
  const chartBg = chartVisible
    ? "var(--color-bg-card)"
    : "var(--color-bg-card-solid, var(--color-bg-card))";

  const chartContent = (
    <div
      style={{
        height: "100%",
        background: chartBg,
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
        </>
      )}
    </div>
  );

  // When defaultFlipped, the chart is the CSS front face so it naturally
  // inherits --color-bg-card transparency from the gauge card. The gauge
  // moves to the CSS back position with the opaque -solid background.
  const front = defaultFlipped ? chartContent : gaugeContent;
  const back = defaultFlipped ? gaugeContent : chartContent;

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
        {/* CSS front face — visible initially */}
        <div style={{ backfaceVisibility: "hidden", height: "100%" }}>
          {front}
        </div>

        {/* CSS back face — hidden initially, visible after flip */}
        <div style={backPositionStyle}>
          {back}
        </div>
      </div>
    </div>
  );
}

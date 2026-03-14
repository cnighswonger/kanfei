/**
 * Modal overlay that shows a 1-hour trend chart for a sensor.
 * Used on mobile as a tap-to-view alternative to FlipTile.
 */
import { useState, useCallback, type ReactNode } from "react";
import { fetchHistory } from "../../api/client.ts";
import TrendChart from "../charts/TrendChart.tsx";

interface TrendModalProps {
  sensor: string;
  label: string;
  unit: string;
  children: ReactNode;
}

export default function TrendModal({
  sensor,
  label,
  unit,
  children,
}: TrendModalProps) {
  const [open, setOpen] = useState(false);
  const [chartData, setChartData] = useState<{ x: number; y: number }[]>([]);
  const [loading, setLoading] = useState(false);

  const handleOpen = useCallback(() => {
    setOpen(true);
    setLoading(true);
    const now = new Date();
    const hourAgo = new Date(now.getTime() - 3_600_000);
    fetchHistory(sensor, hourAgo.toISOString(), now.toISOString(), "raw")
      .then((res) => {
        setChartData(
          res.points
            .map((p) => ({ x: new Date(p.timestamp).getTime(), y: p.value }))
            .filter((pt): pt is { x: number; y: number } => Number.isFinite(pt.x) && Number.isFinite(pt.y)),
        );
      })
      .catch(() => setChartData([]))
      .finally(() => setLoading(false));
  }, [sensor]);

  return (
    <>
      <div onClick={handleOpen} style={{ cursor: "pointer", height: "100%" }}>
        {children}
      </div>

      {open && (
        <div
          onClick={() => setOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 200,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "var(--color-bg-card-solid, var(--color-bg-card))",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--gauge-border-radius, 16px)",
              boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
              padding: "16px",
              width: "92vw",
              maxWidth: 480,
              maxHeight: "80vh",
              overflowY: "auto",
            }}
          >
            <h4
              style={{
                margin: "0 0 8px 0",
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
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  height: 160,
                  color: "var(--color-text-muted)",
                  fontSize: "13px",
                  fontFamily: "var(--font-body)",
                }}
              >
                Loading...
              </div>
            ) : chartData.length > 0 ? (
              <TrendChart title="" data={chartData} unit={unit} height={200} sensor={sensor} />
            ) : (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  height: 160,
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
      )}
    </>
  );
}

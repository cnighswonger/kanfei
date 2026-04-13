/**
 * Wind rose chart — 12-hour polar histogram of wind direction binned by speed.
 * Fetches its own data on mount so it can be dropped into FlipTile/TrendModal
 * as a self-contained backContent node.
 */
import { useState, useEffect, useMemo } from "react";
import Highcharts from "highcharts";
import "highcharts/highcharts-more";
import { HighchartsReact } from "highcharts-react-official";
import { fetchHistory } from "../../api/client.ts";

// --- Constants ---

const SECTORS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
] as const;
const SECTOR_WIDTH = 360 / SECTORS.length; // 22.5

/** Speed bands in display units (mph by default). */
const BANDS = [
  { label: "Calm (0\u20133)",     min: 0,  max: 3,  color: "#93c5fd" },
  { label: "Light (3\u201310)",   min: 3,  max: 10, color: "#3b82f6" },
  { label: "Moderate (10\u201320)", min: 10, max: 20, color: "#f59e0b" },
  { label: "Strong (20+)",       min: 20, max: Infinity, color: "#ef4444" },
];

// --- Helpers ---

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** Assign a direction degree to one of 16 sectors (0 = N, 1 = NNE, ...). */
function dirToSector(deg: number): number {
  // Shift by half a sector so N spans 348.75..11.25
  return Math.round(((deg % 360 + 360) % 360) / SECTOR_WIDTH) % SECTORS.length;
}

interface BinResult {
  /** counts[bandIndex][sectorIndex] = number of observations */
  counts: number[][];
  total: number;
}

function binData(
  dirPoints: { ts: number; val: number }[],
  spdPoints: { ts: number; val: number }[],
): BinResult {
  // Build a timestamp → speed lookup (5m resolution so timestamps align).
  const spdMap = new Map<number, number>();
  for (const p of spdPoints) spdMap.set(p.ts, p.val);

  const counts = BANDS.map(() => new Array(SECTORS.length).fill(0));
  let total = 0;

  for (const dp of dirPoints) {
    const spd = spdMap.get(dp.ts);
    if (spd == null) continue;
    const sector = dirToSector(dp.val);
    for (let b = 0; b < BANDS.length; b++) {
      if (spd >= BANDS[b].min && spd < BANDS[b].max) {
        counts[b][sector]++;
        total++;
        break;
      }
    }
  }
  return { counts, total };
}

// --- Component ---

interface WindRoseProps {
  height?: number;
}

export default function WindRose({ height }: WindRoseProps) {
  const [loading, setLoading] = useState(true);
  const [bins, setBins] = useState<BinResult | null>(null);

  useEffect(() => {
    const now = new Date();
    const halfDay = new Date(now.getTime() - 12 * 3_600_000);
    const start = halfDay.toISOString();
    const end = now.toISOString();

    Promise.all([
      fetchHistory("wind_direction", start, end, "5m"),
      fetchHistory("wind_speed", start, end, "5m"),
    ])
      .then(([dirRes, spdRes]) => {
        const dirPts = dirRes.points
          .filter((p) => p.value != null)
          .map((p) => ({ ts: new Date(p.timestamp).getTime(), val: p.value! }));
        const spdPts = spdRes.points
          .filter((p) => p.value != null)
          .map((p) => ({ ts: new Date(p.timestamp).getTime(), val: p.value! }));
        setBins(binData(dirPts, spdPts));
      })
      .catch(() => setBins(null))
      .finally(() => setLoading(false));
  }, []);

  const options: Highcharts.Options | null = useMemo(() => {
    if (!bins || bins.total === 0) return null;

    const textColor = getCSSVar("--color-text-secondary") || "#9ca3b4";
    const mutedColor = getCSSVar("--color-text-muted") || "#5c6478";
    const borderColor = getCSSVar("--color-border") || "#2a2d3e";

    // Convert counts to percentages of total.
    const pctCounts = bins.counts.map((band) =>
      band.map((c) => Math.round((c / bins.total) * 1000) / 10),
    );

    return {
      chart: {
        polar: true,
        type: "column",
        height: height ?? "100%",
        backgroundColor: "transparent",
        spacing: [4, 4, 4, 4],
        style: {
          fontFamily: getCSSVar("--font-body") || "'Inter', -apple-system, sans-serif",
        },
      },
      title: { text: undefined },
      credits: { enabled: false },
      pane: {
        size: "85%",
      },
      legend: {
        align: "center",
        verticalAlign: "bottom",
        layout: "horizontal",
        itemStyle: { color: textColor, fontSize: "10px", fontWeight: "normal" },
        symbolRadius: 2,
        padding: 0,
        margin: 4,
        itemDistance: 8,
      },
      xAxis: {
        categories: [...SECTORS],
        tickmarkPlacement: "on",
        lineColor: borderColor,
        gridLineColor: borderColor,
        labels: {
          style: { color: mutedColor, fontSize: "10px" },
        },
      },
      yAxis: {
        min: 0,
        endOnTick: false,
        showLastLabel: true,
        gridLineColor: borderColor,
        gridLineInterpolation: "polygon",
        labels: {
          format: "{value}%",
          style: { color: mutedColor, fontSize: "9px" },
        },
        title: { text: undefined },
      },
      tooltip: { enabled: false },
      plotOptions: {
        column: {
          stacking: "normal",
          pointPadding: 0,
          groupPadding: 0,
          borderWidth: 0,
        },
      },
      series: BANDS.map((band, i) => ({
        type: "column" as const,
        name: band.label,
        data: pctCounts[i],
        color: band.color,
      })),
    };
  }, [bins, height]);

  if (loading) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100%", color: "var(--color-text-muted)", fontSize: "13px",
        fontFamily: "var(--font-body)",
      }}>
        Loading...
      </div>
    );
  }

  if (!options) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "center",
        height: "100%", color: "var(--color-text-muted)", fontSize: "13px",
        fontFamily: "var(--font-body)",
      }}>
        No wind data available
      </div>
    );
  }

  return <HighchartsReact highcharts={Highcharts} options={options} />;
}

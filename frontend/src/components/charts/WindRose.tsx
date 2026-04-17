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
import { useTheme } from "../../context/ThemeContext.tsx";

// --- Constants ---

const SECTORS = [
  "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
  "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
] as const;
const SECTOR_WIDTH = 360 / SECTORS.length; // 22.5

/** Speed bands in display units (mph by default). Zero-speed readings
 *  are filtered out entirely — see binData. */
const BAND_DEFS = [
  { label: "Light (<7)",     min: 0,  max: 7,  cssVar: "--color-wind-light",  themeVar: "",               fallback: "#93c5fd" },
  { label: "Breezy (7\u201315)",  min: 7,  max: 15, cssVar: "--color-wind-breezy", themeVar: "--color-accent",  fallback: "#3b82f6" },
  { label: "Windy (15\u201325)",  min: 15, max: 25, cssVar: "--color-wind-windy",  themeVar: "--color-warning", fallback: "#f59e0b" },
  { label: "Strong (25+)",   min: 25, max: Infinity, cssVar: "--color-wind-strong", themeVar: "--color-danger",  fallback: "#ef4444" },
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

  const counts = BAND_DEFS.map(() => new Array(SECTORS.length).fill(0));
  let total = 0;

  for (const dp of dirPoints) {
    const spd = spdMap.get(dp.ts);
    if (spd == null) continue;
    // Skip calm readings — wind direction is unreliable when speed is 0
    // (Davis stations hold the last direction, producing a stuck-bar artifact).
    if (spd <= 0) continue;
    const sector = dirToSector(dp.val);
    for (let b = 0; b < BAND_DEFS.length; b++) {
      if (spd >= BAND_DEFS[b].min && spd < BAND_DEFS[b].max) {
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

const REFRESH_MS = 60_000; // 1 minute

export default function WindRose({ height }: WindRoseProps) {
  const { themeName } = useTheme();
  const [loading, setLoading] = useState(true);
  const [bins, setBins] = useState<BinResult | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    function fetchData() {
      const now = new Date();
      const windowStart = new Date(now.getTime() - 3 * 3_600_000);
      const start = windowStart.toISOString();
      const end = now.toISOString();

      Promise.all([
        fetchHistory("wind_direction", start, end, "5m"),
        fetchHistory("wind_speed", start, end, "5m"),
      ])
        .then(([dirRes, spdRes]) => {
          if (cancelled) return;
          const dirPts = dirRes.points
            .filter((p) => p.value != null)
            .map((p) => ({ ts: new Date(p.timestamp).getTime(), val: p.value! }));
          const spdPts = spdRes.points
            .filter((p) => p.value != null)
            .map((p) => ({ ts: new Date(p.timestamp).getTime(), val: p.value! }));
          setBins(binData(dirPts, spdPts));
          setLastUpdate(new Date());
        })
        .catch(() => { if (!cancelled) setBins(null); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }

    fetchData();
    const timer = setInterval(fetchData, REFRESH_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);

  const options: Highcharts.Options | null = useMemo(() => {
    if (!bins || bins.total === 0) return null;

    const textColor = getCSSVar("--color-text-secondary") || "#9ca3b4";

    const bandColors = BAND_DEFS.map((b) =>
      getCSSVar(b.cssVar) || (b.themeVar && getCSSVar(b.themeVar)) || b.fallback,
    );

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
        lineColor: textColor,
        gridLineColor: textColor,
        labels: {
          style: { color: textColor, fontSize: "10px" },
        },
      },
      yAxis: {
        min: 0,
        endOnTick: false,
        showLastLabel: true,
        gridLineColor: textColor,
        gridLineInterpolation: "polygon",
        labels: {
          format: "{value}%",
          style: { color: textColor, fontSize: "9px" },
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
      series: BAND_DEFS.map((band, i) => ({
        type: "column" as const,
        name: band.label,
        data: pctCounts[i],
        color: bandColors[i],
      })),
    };
  }, [bins, height, themeName]);

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
        Calm — no wind in last 3h
      </div>
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <HighchartsReact highcharts={Highcharts} options={options} />
      </div>
      {lastUpdate && (
        <div style={{
          textAlign: "center",
          fontSize: "9px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-muted)",
          padding: "2px 0 0",
        }}>
          3h distribution (calm filtered) — updated {lastUpdate.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        </div>
      )}
    </div>
  );
}

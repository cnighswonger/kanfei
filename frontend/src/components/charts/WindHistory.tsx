/**
 * Dual-panel wind history chart: direction scatter (top) + speed/gust columns (bottom).
 * Self-contained — fetches its own data and auto-refreshes every 60 seconds.
 */
import { useState, useEffect, useMemo } from "react";
import Highcharts from "highcharts";
import { HighchartsReact } from "highcharts-react-official";
import { fetchHistory } from "../../api/client.ts";
import { useTheme } from "../../context/ThemeContext.tsx";
import { getHighchartsTimeConfig } from "../../utils/timezone.ts";

// --- Helpers ---

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

interface DataPoint {
  ts: number;
  val: number;
}

// --- Component ---

interface WindHistoryProps {
  hours?: number;
  height?: number;
}

const REFRESH_MS = 60_000;

export default function WindHistory({ hours = 4, height }: WindHistoryProps) {
  const { themeName } = useTheme();
  const [loading, setLoading] = useState(true);
  const [spdPts, setSpdPts] = useState<DataPoint[]>([]);
  const [gustPts, setGustPts] = useState<DataPoint[]>([]);
  const [dirPts, setDirPts] = useState<DataPoint[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  useEffect(() => {
    let cancelled = false;

    function fetchData() {
      const now = new Date();
      const windowStart = new Date(now.getTime() - hours * 3_600_000);
      const start = windowStart.toISOString();
      const end = now.toISOString();

      Promise.all([
        fetchHistory("wind_speed", start, end, "5m"),
        fetchHistory("wind_gust", start, end, "5m"),
        fetchHistory("wind_direction", start, end, "5m"),
      ])
        .then(([spdRes, gustRes, dirRes]) => {
          if (cancelled) return;
          const toPoints = (res: typeof spdRes) =>
            res.points
              .filter((p) => p.value != null)
              .map((p) => ({ ts: new Date(p.timestamp).getTime(), val: p.value! }));
          setSpdPts(toPoints(spdRes));
          setGustPts(toPoints(gustRes));
          setDirPts(toPoints(dirRes));
          setLastUpdate(new Date());
        })
        .catch(() => {
          if (!cancelled) {
            setSpdPts([]);
            setGustPts([]);
            setDirPts([]);
          }
        })
        .finally(() => { if (!cancelled) setLoading(false); });
    }

    fetchData();
    const timer = setInterval(fetchData, REFRESH_MS);
    return () => { cancelled = true; clearInterval(timer); };
  }, [hours]);

  const options: Highcharts.Options | null = useMemo(() => {
    if (spdPts.length === 0 && dirPts.length === 0) return null;

    const textMuted = getCSSVar("--color-text-muted") || "#6b7280";
    const speedColor = getCSSVar("--color-wind-breezy") || getCSSVar("--color-accent") || "#3b82f6";
    const gustColor = getCSSVar("--color-wind-light") || "#93c5fd";
    const dirColor = getCSSVar("--color-danger") || "#ef4444";
    const borderColor = getCSSVar("--color-border") || "#374151";
    const fontFamily = getCSSVar("--font-body") || "'Inter', -apple-system, sans-serif";

    const dirData: [number, number][] = dirPts.map((p) => [p.ts, p.val]);
    const spdData: [number, number][] = spdPts.map((p) => [p.ts, p.val]);
    const gustData: [number, number][] = gustPts.map((p) => [p.ts, p.val]);

    return {
      chart: {
        height: height ?? "100%",
        backgroundColor: "transparent",
        spacing: [4, 8, 4, 4],
        style: { fontFamily },
      },
      title: { text: undefined },
      credits: { enabled: false },
      legend: { enabled: false },
      time: getHighchartsTimeConfig(),

      xAxis: {
        type: "datetime",
        lineColor: borderColor,
        tickColor: borderColor,
        labels: {
          style: { color: textMuted, fontSize: "9px" },
        },
        crosshair: true,
      },

      yAxis: [
        {
          // Top panel: wind direction (0-360°)
          top: "0%",
          height: "30%",
          offset: 0,
          opposite: true,
          min: 0,
          max: 360,
          tickPositions: [0, 90, 180, 270, 360],
          labels: {
            formatter: function (this: Highcharts.AxisLabelsFormatterContextObject) {
              const cardinals: Record<number, string> = { 0: "N", 90: "E", 180: "S", 270: "W", 360: "N" };
              return cardinals[this.value as number] ?? "";
            },
            style: { color: textMuted, fontSize: "9px" },
          },
          title: { text: undefined },
          gridLineColor: borderColor,
          gridLineWidth: 1,
          gridLineDashStyle: "Dot",
          lineColor: borderColor,
          lineWidth: 1,
        },
        {
          // Bottom panel: speed + gust (mph)
          top: "35%",
          height: "65%",
          offset: 0,
          opposite: true,
          min: 0,
          softMax: 15,
          labels: {
            style: { color: textMuted, fontSize: "9px" },
          },
          title: { text: undefined },
          gridLineColor: borderColor,
          gridLineWidth: 1,
          gridLineDashStyle: "Dot",
          lineColor: borderColor,
          lineWidth: 1,
        },
      ],

      tooltip: {
        shared: true,
        backgroundColor: "rgba(0,0,0,0.85)",
        borderColor: borderColor,
        style: { color: "#e5e7eb", fontSize: "11px", fontFamily },
        xDateFormat: "%l:%M %p",
        pointFormatter: function (this: Highcharts.Point): string {
          const name = this.series.name;
          const color = this.series.color;
          if (name === "Direction") {
            const deg = this.y ?? 0;
            const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
            const idx = Math.round(((deg % 360 + 360) % 360) / 22.5) % 16;
            return `<span style="color:${color}">●</span> ${name}: <b>${dirs[idx]} (${deg}°)</b><br/>`;
          }
          return `<span style="color:${color}">●</span> ${name}: <b>${this.y} mph</b><br/>`;
        },
      },

      plotOptions: {
        column: {
          borderWidth: 0,
          pointPadding: 0,
          groupPadding: 0.1,
        },
        scatter: {
          marker: {
            radius: 2,
            symbol: "circle",
          },
        },
      },

      series: [
        {
          type: "scatter",
          name: "Direction",
          data: dirData,
          yAxis: 0,
          color: dirColor,
          marker: { radius: 2 },
          zIndex: 2,
        },
        {
          type: "column",
          name: "Gust",
          data: gustData,
          yAxis: 1,
          color: gustColor,
          zIndex: 0,
        },
        {
          type: "column",
          name: "Speed",
          data: spdData,
          yAxis: 1,
          color: speedColor,
          zIndex: 1,
        },
      ],
    };
  }, [spdPts, gustPts, dirPts, height, themeName]);

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
          {hours}h history — updated {lastUpdate.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
        </div>
      )}
    </div>
  );
}

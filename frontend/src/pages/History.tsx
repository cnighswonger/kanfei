import { useState, useMemo } from "react";
import Highcharts from "highcharts";
import HighchartsReact from "highcharts-react-official";
import { useHistoricalData } from "../hooks/useHistoricalData.ts";
import {
  SENSOR_DISPLAY_NAMES,
  UNIT_LABELS,
} from "../utils/constants.ts";
import { getHighchartsTimeConfig, resolveTimezone } from "../utils/timezone.ts";
import { computeYAxisScale } from "../utils/chartScaling.ts";
import { useIsMobile } from "../hooks/useIsMobile.ts";

// --- Sensor unit mapping (sensor key -> unit string) ---

const SENSOR_UNITS: Record<string, string> = {
  temperature_inside: "F",
  temperature_outside: "F",
  humidity_inside: "%",
  humidity_outside: "%",
  wind_speed: "mph",
  wind_direction: "deg",
  barometer: "inHg",
  rain_daily: "in",
  rain_yearly: "in",
  rain_rate: "in",
  solar_radiation: "W/m\u00B2",
  uv_index: "",
  heat_index: "F",
  dew_point: "F",
  wind_chill: "F",
  feels_like: "F",
};

// --- Date range helpers ---

type Preset = "1h" | "12h" | "24h" | "7d" | "30d" | "custom";

function isoLocal(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function presetRange(preset: Preset): { start: string; end: string } {
  const now = new Date();
  const end = now.toISOString();
  let start: Date;
  switch (preset) {
    case "1h":
      start = new Date(now.getTime() - 1 * 60 * 60 * 1000);
      break;
    case "12h":
      start = new Date(now.getTime() - 12 * 60 * 60 * 1000);
      break;
    case "24h":
      start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      break;
    case "7d":
      start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      break;
    case "30d":
      start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      break;
    default:
      start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  }
  return { start: start.toISOString(), end };
}

// --- Shared styles ---

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const labelStyle: React.CSSProperties = {
  fontSize: "13px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "6px",
  display: "block",
};

const selectStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  cursor: "pointer",
  minWidth: "180px",
};

const presetBtnBase: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "13px",
  padding: "6px 14px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  cursor: "pointer",
  transition: "background 0.15s, color 0.15s",
};

const inputStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  colorScheme: "dark",
};

// --- Component ---

export default function History() {
  const isMobile = useIsMobile();
  const sensorKeys = Object.keys(SENSOR_DISPLAY_NAMES);
  const [sensor, setSensor] = useState(sensorKeys[0] ?? "temperature_inside");
  const [preset, setPreset] = useState<Preset>("24h");
  const [resolution, setResolution] = useState("5m");

  // Custom date range state
  const defaultCustom = presetRange("24h");
  const [customStart, setCustomStart] = useState(
    isoLocal(new Date(defaultCustom.start)),
  );
  const [customEnd, setCustomEnd] = useState(
    isoLocal(new Date(defaultCustom.end)),
  );

  // Compute effective start/end
  const { start, end } = useMemo(() => {
    if (preset === "custom") {
      return {
        start: new Date(customStart).toISOString(),
        end: new Date(customEnd).toISOString(),
      };
    }
    return presetRange(preset);
  }, [preset, customStart, customEnd]);

  const { data, summary, loading, error } = useHistoricalData(
    sensor,
    start,
    end,
    resolution,
  );

  // Build Highcharts options
  const tz = resolveTimezone();
  const chartOptions: Highcharts.Options = useMemo(() => {
    const root = document.documentElement;
    const cs = getComputedStyle(root);
    const textColor = cs.getPropertyValue("--color-text").trim();
    const textMuted = cs.getPropertyValue("--color-text-muted").trim();
    const accent = cs.getPropertyValue("--color-accent").trim();
    const bgCard = cs.getPropertyValue("--color-bg-card-solid").trim() || cs.getPropertyValue("--color-bg-card").trim();
    const borderColor = cs.getPropertyValue("--color-border").trim();

    const unitKey = SENSOR_UNITS[sensor] ?? "";
    const unitLabel = UNIT_LABELS[unitKey] ?? (unitKey ? ` ${unitKey}` : "");

    const seriesData: [number, number | null][] = data
      .map((p) => {
        const x = new Date(p.timestamp).getTime();
        if (!Number.isFinite(x)) return null;
        const y = (p.value != null && Number.isFinite(p.value)) ? p.value : null;
        return [x, y] as [number, number | null];
      })
      .filter((pt): pt is [number, number | null] => pt !== null);

    // Use true min/max from API summary when available (aggregated data
    // returns bucket averages, so point values don't reflect true extremes)
    const yValues: number[] = [];
    if (summary?.min != null) yValues.push(summary.min);
    if (summary?.max != null) yValues.push(summary.max);
    if (yValues.length === 0) {
      // Fallback to point values (raw resolution or missing summary)
      for (const [, y] of seriesData) {
        if (y !== null && Number.isFinite(y)) yValues.push(y);
      }
    }
    const yScale = computeYAxisScale(sensor, yValues);

    return {
      time: getHighchartsTimeConfig(),
      chart: {
        type: "areaspline",
        height: isMobile ? 280 : 400,
        backgroundColor: bgCard,
        style: { fontFamily: "var(--font-body)" },
        zooming: { type: "x" },
        ...(isMobile ? { spacing: [8, 4, 8, 4] } : {}),
      },
      title: { text: undefined },
      accessibility: { enabled: false },
      credits: { enabled: false },
      xAxis: {
        type: "datetime",
        lineColor: borderColor,
        tickColor: borderColor,
        labels: { style: { color: textMuted, fontSize: isMobile ? "9px" : "11px" } },
        crosshair: true,
      },
      yAxis: {
        title: isMobile
          ? { text: undefined }
          : {
              text: `${SENSOR_DISPLAY_NAMES[sensor] ?? sensor} (${unitLabel.trim()})`,
              style: { color: textMuted, fontSize: "12px" },
            },
        gridLineColor: borderColor,
        labels: { style: { color: textMuted, fontSize: isMobile ? "9px" : "11px" } },
        softMin: yScale.softMin,
        softMax: yScale.softMax,
        ...(yScale.tickInterval != null && { tickInterval: yScale.tickInterval }),
      },
      legend: { enabled: false },
      tooltip: {
        shared: true,
        valueSuffix: unitLabel,
        backgroundColor: bgCard,
        borderColor: borderColor,
        style: { color: textColor, fontSize: "12px" },
        xDateFormat: "%b %e, %Y %l:%M %p",
      },
      plotOptions: {
        areaspline: {
          fillOpacity: 0.15,
          lineWidth: 2,
          marker: { enabled: false, radius: 3 },
          states: { hover: { lineWidth: 3 } },
          threshold: null,
        },
      },
      series: [
        {
          type: "areaspline" as const,
          name: SENSOR_DISPLAY_NAMES[sensor] ?? sensor,
          data: seriesData,
          color: accent,
        },
      ],
    };
  }, [data, summary, sensor, tz, isMobile]);

  const presets: { key: Preset; label: string }[] = [
    { key: "1h", label: "1 Hour" },
    { key: "12h", label: "12 Hours" },
    { key: "24h", label: "24 Hours" },
    { key: "7d", label: "7 Days" },
    { key: "30d", label: "30 Days" },
    { key: "custom", label: "Custom" },
  ];

  const resolutions = [
    { value: "raw", label: "Raw" },
    { value: "5m", label: "5 min" },
    { value: "hourly", label: "Hourly" },
    { value: "daily", label: "Daily" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
        <h2
          className="dashboard-heading"
          style={{
            margin: "0 0 16px 0",
            fontSize: "24px",
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          History
        </h2>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
      {/* Controls card */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <div
          style={{
            display: "flex",
            flexDirection: isMobile ? "column" : "row",
            flexWrap: "wrap",
            gap: isMobile ? "12px" : "16px",
            alignItems: isMobile ? "stretch" : "flex-end",
          }}
        >
          {/* Sensor selector */}
          <div>
            <label style={labelStyle}>Sensor</label>
            <select
              style={{ ...selectStyle, width: isMobile ? "100%" : undefined, minWidth: isMobile ? 0 : "180px" }}
              value={sensor}
              onChange={(e) => setSensor(e.target.value)}
            >
              {sensorKeys.map((key) => (
                <option key={key} value={key}>
                  {SENSOR_DISPLAY_NAMES[key]}
                </option>
              ))}
            </select>
          </div>

          {/* Date range presets */}
          <div>
            <label style={labelStyle}>Date Range</label>
            <div style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "repeat(3, 1fr)" : "repeat(6, auto)",
              gap: "6px",
            }}>
              {presets.map((p) => (
                <button
                  key={p.key}
                  style={{
                    ...presetBtnBase,
                    padding: isMobile ? "8px 6px" : "6px 14px",
                    fontSize: isMobile ? "12px" : "13px",
                    background:
                      preset === p.key
                        ? "var(--color-accent)"
                        : "var(--color-bg-secondary)",
                    color:
                      preset === p.key
                        ? "#fff"
                        : "var(--color-text-secondary)",
                    borderColor:
                      preset === p.key
                        ? "var(--color-accent)"
                        : "var(--color-border)",
                  }}
                  onClick={() => setPreset(p.key)}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {/* Resolution + CSV row */}
          <div style={{
            display: "flex",
            gap: isMobile ? "10px" : "16px",
            alignItems: "flex-end",
          }}>
            <div style={{ flex: isMobile ? 1 : undefined }}>
              <label style={labelStyle}>Resolution</label>
              <select
                style={{ ...selectStyle, width: isMobile ? "100%" : undefined, minWidth: isMobile ? 0 : "180px" }}
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
              >
                {resolutions.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              {!isMobile && <label style={labelStyle}>&nbsp;</label>}
              <a
                href={`/api/export?sensors=${encodeURIComponent(sensor)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&resolution=${encodeURIComponent(resolution)}`}
                download
                style={{
                  ...presetBtnBase,
                  padding: isMobile ? "8px 12px" : "6px 14px",
                  background: "var(--color-bg-secondary)",
                  color: "var(--color-text-secondary)",
                  textDecoration: "none",
                  display: "inline-block",
                  whiteSpace: "nowrap",
                }}
              >
                CSV
              </a>
            </div>
          </div>
        </div>

        {/* Custom date inputs */}
        {preset === "custom" && (
          <div
            style={{
              display: "flex",
              flexDirection: isMobile ? "column" : "row",
              gap: isMobile ? "10px" : "16px",
              marginTop: "12px",
              flexWrap: "wrap",
              alignItems: isMobile ? "stretch" : "flex-end",
            }}
          >
            <div>
              <label style={labelStyle}>Start</label>
              <input
                type="datetime-local"
                style={{ ...inputStyle, width: isMobile ? "100%" : undefined }}
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
              />
            </div>
            <div>
              <label style={labelStyle}>End</label>
              <input
                type="datetime-local"
                style={{ ...inputStyle, width: isMobile ? "100%" : undefined }}
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
              />
            </div>
          </div>
        )}
      </div>

      {/* Summary stats bar */}
      {!loading && !error && summary && (summary.min != null || summary.max != null) && (
        <div
          style={{
            ...cardStyle,
            padding: isMobile ? "10px 12px" : "12px 20px",
            display: "flex",
            gap: isMobile ? "16px" : "32px",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {summary.max != null && (
            <div>
              <span style={{ fontSize: "11px", fontFamily: "var(--font-body)", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>High </span>
              <span style={{ fontSize: "16px", fontFamily: "var(--font-heading)", color: "var(--color-text)", fontWeight: "bold" }}>
                {summary.max}{(UNIT_LABELS[SENSOR_UNITS[sensor] ?? ""] ?? "").trim()}
              </span>
            </div>
          )}
          {summary.min != null && (
            <div>
              <span style={{ fontSize: "11px", fontFamily: "var(--font-body)", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Low </span>
              <span style={{ fontSize: "16px", fontFamily: "var(--font-heading)", color: "var(--color-text)", fontWeight: "bold" }}>
                {summary.min}{(UNIT_LABELS[SENSOR_UNITS[sensor] ?? ""] ?? "").trim()}
              </span>
            </div>
          )}
          {summary.avg != null && (
            <div>
              <span style={{ fontSize: "11px", fontFamily: "var(--font-body)", color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Avg </span>
              <span style={{ fontSize: "16px", fontFamily: "var(--font-heading)", color: "var(--color-text)", fontWeight: "bold" }}>
                {summary.avg}{(UNIT_LABELS[SENSOR_UNITS[sensor] ?? ""] ?? "").trim()}
              </span>
            </div>
          )}
          {summary.count > 0 && (
            <div style={{ marginLeft: "auto" }}>
              <span style={{ fontSize: "11px", fontFamily: "var(--font-body)", color: "var(--color-text-muted)" }}>
                {summary.count.toLocaleString()} points
              </span>
            </div>
          )}
        </div>
      )}

      {/* Chart area */}
      <div style={cardStyle}>
        {loading && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: isMobile ? "280px" : "400px",
            }}
          >
            <div
              style={{
                width: "36px",
                height: "36px",
                border: "3px solid var(--color-border)",
                borderTopColor: "var(--color-accent)",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
              }}
            />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {error && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: isMobile ? "280px" : "400px",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <span
              style={{ color: "var(--color-danger)", fontSize: "16px" }}
            >
              Failed to load data
            </span>
            <span
              style={{
                color: "var(--color-text-muted)",
                fontSize: "13px",
                maxWidth: "400px",
                textAlign: "center",
              }}
            >
              {error}
            </span>
          </div>
        )}

        {!loading && !error && data.length === 0 && (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: isMobile ? "280px" : "400px",
              color: "var(--color-text-muted)",
              fontSize: "14px",
            }}
          >
            No data available for the selected range.
          </div>
        )}

        {!loading && !error && data.length > 0 && (
          <HighchartsReact highcharts={Highcharts} options={chartOptions} />
        )}
      </div>
      </div>
    </div>
  );
}

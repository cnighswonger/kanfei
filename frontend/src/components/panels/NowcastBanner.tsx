/**
 * Full-width nowcast summary banner for the Dashboard.
 * Renders above the tile grid when nowcast data is available.
 * Clicking navigates to the full /nowcast page.
 */
import { useWeatherData } from "../../context/WeatherDataContext.tsx";
import { useIsMobile } from "../../hooks/useIsMobile.ts";

function normalizeConfidence(c: string): string {
  const upper = (c ?? "").toUpperCase();
  if (upper.startsWith("HIGH")) return "HIGH";
  if (upper.startsWith("MEDIUM")) return "MEDIUM";
  if (upper.startsWith("LOW")) return "LOW";
  return upper;
}

function confidenceColor(c: string): string {
  switch (normalizeConfidence(c)) {
    case "HIGH":
      return "var(--color-success)";
    case "MEDIUM":
      return "var(--color-warning, #f59e0b)";
    case "LOW":
      return "var(--color-danger)";
    default:
      return "var(--color-text-muted)";
  }
}

function timeAgo(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export default function NowcastBanner() {
  const { nowcast } = useWeatherData();
  const isMobile = useIsMobile();

  if (!nowcast) return null;

  const MAX_AGE_MS = 4 * 60 * 60 * 1000; // 4 hours
  const age = Date.now() - new Date(nowcast.created_at).getTime();
  if (age > MAX_AGE_MS) return null;

  const elements = nowcast.elements || {};
  const overallConfidence =
    elements.precipitation?.confidence ||
    elements.temperature?.confidence ||
    "MEDIUM";
  const precipTiming = elements.precipitation?.timing;

  return (
    <div
      onClick={() => { window.location.href = "/nowcast"; }}
      role="link"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") window.location.href = "/nowcast";
      }}
      style={{
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        border: "1px solid var(--color-border)",
        borderLeft: "4px solid var(--color-accent)",
        boxShadow: "var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))",
        padding: isMobile ? "12px" : "16px 20px",
        marginBottom: "16px",
        cursor: "pointer",
        transition: "border-color 0.15s",
      }}
    >
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "8px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span
            style={{
              fontSize: "12px",
              fontFamily: "var(--font-body)",
              color: "var(--color-text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
              fontWeight: 600,
            }}
          >
            AI Nowcast
          </span>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "var(--font-body)",
              color: "var(--color-text-muted)",
            }}
          >
            {timeAgo(nowcast.created_at)}
          </span>
        </div>

        {/* Confidence dot */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "11px",
            fontFamily: "var(--font-body)",
            color: "var(--color-text-muted)",
          }}
        >
          <span
            style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: confidenceColor(overallConfidence),
              flexShrink: 0,
            }}
          />
          {normalizeConfidence(overallConfidence)}
        </div>
      </div>

      {/* Summary text */}
      <p
        style={{
          margin: 0,
          fontSize: isMobile ? "13px" : "14px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text)",
          lineHeight: 1.6,
        }}
      >
        {nowcast.summary}
      </p>

      {/* Precipitation timing */}
      {precipTiming && (
        <div
          style={{
            marginTop: "8px",
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            color: "var(--color-rain-blue, var(--color-accent))",
            padding: "4px 8px",
            background: "var(--color-bg-secondary)",
            borderRadius: "4px",
            display: "inline-block",
          }}
        >
          {precipTiming}
        </div>
      )}
    </div>
  );
}

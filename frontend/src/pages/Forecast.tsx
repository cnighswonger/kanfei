import { useWeatherData } from "../context/WeatherDataContext.tsx";
import { formatTimestamp } from "../utils/formatting.ts";
import { useIsMobile } from "../hooks/useIsMobile.ts";
import type { NWSPeriod } from "../api/types.ts";

// --- Shared styles ---

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 16px 0",
  fontSize: "18px",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const mutedText: React.CSSProperties = {
  color: "var(--color-text-muted)",
  fontSize: "13px",
  fontFamily: "var(--font-body)",
};

const emptyState: React.CSSProperties = {
  padding: "32px 0",
  textAlign: "center" as const,
  color: "var(--color-text-muted)",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
};

// --- Sub-components ---

function ZambrettiSection({
  text,
  confidence,
  updated,
  isMobile,
}: {
  text: string;
  confidence: number;
  updated: string;
  isMobile?: boolean;
}) {
  // Determine confidence color
  let barColor = "var(--color-success)";
  if (confidence < 40) barColor = "var(--color-danger)";
  else if (confidence < 70) barColor = "var(--color-warning)";

  return (
    <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={{ ...sectionTitle, fontSize: isMobile ? "16px" : "18px" }}>Local Forecast (Zambretti)</h3>

      {/* Forecast text */}
      <p
        style={{
          margin: "0 0 16px 0",
          fontSize: "16px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text)",
          lineHeight: "1.5",
        }}
      >
        {text}
      </p>

      {/* Confidence bar */}
      <div style={{ marginBottom: "12px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: "6px",
          }}
        >
          <span style={mutedText}>Confidence</span>
          <span
            style={{
              fontSize: "13px",
              fontFamily: "var(--font-mono)",
              color: "var(--color-text-secondary)",
            }}
          >
            {confidence}%
          </span>
        </div>
        <div
          style={{
            height: "8px",
            borderRadius: "4px",
            background: "var(--color-gauge-track)",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${Math.max(0, Math.min(100, confidence))}%`,
              borderRadius: "4px",
              background: barColor,
              transition: "width 0.4s ease",
            }}
          />
        </div>
      </div>

      {/* Updated time */}
      <span style={mutedText}>Updated {formatTimestamp(updated)}</span>
    </div>
  );
}

function NWSPeriodCard({ period, isMobile }: { period: NWSPeriod; isMobile?: boolean }) {
  return (
    <div
      style={{
        background: "var(--color-bg-secondary)",
        borderRadius: "var(--gauge-border-radius)",
        border: "1px solid var(--color-border-light)",
        padding: isMobile ? "10px 12px" : "16px",
        display: "flex",
        flexDirection: "column",
        gap: isMobile ? "6px" : "8px",
        minWidth: 0,
      }}
    >
      {/* Header row: icon + name + short forecast */}
      <div style={{ display: "flex", alignItems: "center", gap: isMobile ? "8px" : "10px", minWidth: 0 }}>
        {period.icon_url && (
          <img
            src={period.icon_url}
            alt={period.short_forecast || period.name}
            style={{
              width: isMobile ? "40px" : "48px",
              height: isMobile ? "40px" : "48px",
              borderRadius: "6px",
              flexShrink: 0,
            }}
          />
        )}
        <div style={{ minWidth: 0 }}>
          <h4
            style={{
              margin: 0,
              fontSize: isMobile ? "14px" : "15px",
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            {period.name}
          </h4>
          {period.short_forecast && (
            <span
              style={{
                fontSize: isMobile ? "11px" : "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-muted)",
                display: "block",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {period.short_forecast}
            </span>
          )}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          gap: isMobile ? "10px" : "16px",
          flexWrap: "wrap",
          fontSize: isMobile ? "12px" : "13px",
          fontFamily: "var(--font-body)",
        }}
      >
        <span style={{ color: "var(--color-temp-hot)" }}>
          {period.temperature}&deg;F
        </span>
        <span style={{ color: "var(--color-text-secondary)" }}>
          Wind: {period.wind}
        </span>
        {period.precipitation_pct > 0 && (
          <span style={{ color: "var(--color-rain-blue)" }}>
            Precip: {period.precipitation_pct}%
          </span>
        )}
      </div>

      <p
        style={{
          margin: 0,
          fontSize: isMobile ? "12px" : "13px",
          lineHeight: "1.45",
          color: "var(--color-text-secondary)",
          fontFamily: "var(--font-body)",
        }}
      >
        {period.text}
      </p>
    </div>
  );
}

// --- Main component ---

export default function Forecast() {
  const isMobile = useIsMobile();
  const { forecast, refreshForecast } = useWeatherData();

  const local = forecast?.local ?? null;
  const nws = forecast?.nws ?? null;

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div
        style={{
          flexShrink: 0,
          padding: "24px 24px 0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <h2
          style={{
            margin: 0,
            fontSize: "24px",
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Forecast
        </h2>
        <button
          onClick={refreshForecast}
          style={{
            background: "var(--color-bg-card)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--gauge-border-radius)",
            color: "var(--color-text-secondary)",
            padding: "6px 14px",
            fontSize: "13px",
            fontFamily: "var(--font-body)",
            cursor: "pointer",
          }}
          title="Refresh forecast data"
        >
          Refresh
        </button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
      {/* Zambretti local forecast */}
      {local ? (
        <ZambrettiSection
          text={local.text}
          confidence={local.confidence}
          updated={local.updated}
          isMobile={isMobile}
        />
      ) : (
        <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
          <h3 style={{ ...sectionTitle, fontSize: isMobile ? "16px" : "18px" }}>Local Forecast (Zambretti)</h3>
          <div style={emptyState}>
            No local forecast available. The Zambretti algorithm requires
            barometric pressure history to generate predictions.
          </div>
        </div>
      )}

      {/* NWS forecast */}
      {nws && nws.periods.length > 0 ? (
        <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              marginBottom: isMobile ? "10px" : "16px",
            }}
          >
            <h3 style={{ ...sectionTitle, margin: 0, fontSize: isMobile ? "16px" : "18px" }}>
              NWS Forecast
            </h3>
            <span style={mutedText}>
              Updated {formatTimestamp(nws.updated)}
            </span>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: isMobile
                ? "1fr"
                : "repeat(auto-fill, minmax(280px, 1fr))",
              gap: isMobile ? "10px" : "12px",
            }}
          >
            {nws.periods.map((period, idx) => (
              <NWSPeriodCard key={idx} period={period} isMobile={isMobile} />
            ))}
          </div>
        </div>
      ) : (
        <div style={cardStyle}>
          <h3 style={sectionTitle}>NWS Forecast</h3>
          <div style={emptyState}>
            No NWS forecast data available. Ensure NWS integration is enabled
            in Settings and a valid location is configured.
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

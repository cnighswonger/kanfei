import { useMemo } from "react";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import type { SunData, MoonData } from "../api/types.ts";

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

const dataRow: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "8px 0",
  borderBottom: "1px solid var(--color-border-light)",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
};

const dataLabel: React.CSSProperties = {
  color: "var(--color-text-secondary)",
};

const dataValue: React.CSSProperties = {
  color: "var(--color-text)",
  fontFamily: "var(--font-mono)",
};

const emptyState: React.CSSProperties = {
  padding: "32px 0",
  textAlign: "center" as const,
  color: "var(--color-text-muted)",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
};

// --- Sun arc SVG ---

function SunArc({ sunrise, sunset }: { sunrise: string; sunset: string }) {
  // Parse time strings (expected format: "HH:MM AM/PM" or ISO)
  const parseTimeToMinutes = (timeStr: string): number => {
    const d = new Date(timeStr);
    if (!isNaN(d.getTime())) {
      return d.getHours() * 60 + d.getMinutes();
    }
    // Fallback: parse "7:05 AM" style
    const match = timeStr.match(/(\d+):(\d+)\s*(AM|PM)?/i);
    if (!match) return 0;
    let hours = parseInt(match[1], 10);
    const minutes = parseInt(match[2], 10);
    const ampm = match[3]?.toUpperCase();
    if (ampm === "PM" && hours !== 12) hours += 12;
    if (ampm === "AM" && hours === 12) hours = 0;
    return hours * 60 + minutes;
  };

  const sunriseMin = parseTimeToMinutes(sunrise);
  const sunsetMin = parseTimeToMinutes(sunset);
  const now = new Date();
  const nowMin = now.getHours() * 60 + now.getMinutes();

  const width = 320;
  const height = 170;
  const cx = width / 2;
  const cy = height - 20;
  const rx = 140;
  const ry = 120;

  // Fraction of day elapsed (0 = sunrise, 1 = sunset)
  const dayLength = sunsetMin - sunriseMin;
  let fraction = dayLength > 0 ? (nowMin - sunriseMin) / dayLength : 0.5;
  fraction = Math.max(0, Math.min(1, fraction));

  const isDaytime = nowMin >= sunriseMin && nowMin <= sunsetMin;

  // Sun position on the arc (angle from left to right = pi to 0)
  const angle = Math.PI * (1 - fraction);
  const sunX = cx + rx * Math.cos(angle);
  const sunY = cy - ry * Math.sin(angle);

  // Arc path (semicircle from left to right)
  const arcStartX = cx - rx;
  const arcEndX = cx + rx;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width="100%"
      style={{ maxWidth: "320px", display: "block", margin: "8px auto" }}
    >
      {/* Horizon line */}
      <line
        x1={cx - rx - 10}
        y1={cy}
        x2={cx + rx + 10}
        y2={cy}
        stroke="var(--color-border)"
        strokeWidth="1"
      />

      {/* Arc path */}
      <path
        d={`M ${arcStartX} ${cy} A ${rx} ${ry} 0 0 1 ${arcEndX} ${cy}`}
        fill="none"
        stroke="var(--color-solar-yellow)"
        strokeWidth="1.5"
        strokeDasharray="4 3"
        opacity="0.5"
      />

      {/* Sun dot (only if daytime) */}
      {isDaytime && (
        <>
          <circle
            cx={sunX}
            cy={sunY}
            r="10"
            fill="var(--color-solar-yellow)"
            opacity="0.25"
          />
          <circle
            cx={sunX}
            cy={sunY}
            r="5"
            fill="var(--color-solar-yellow)"
          />
        </>
      )}

      {/* Sunrise label */}
      <text
        x={arcStartX}
        y={cy + 14}
        textAnchor="middle"
        fill="var(--color-text-muted)"
        fontSize="10"
        fontFamily="var(--font-body)"
      >
        Rise
      </text>

      {/* Sunset label */}
      <text
        x={arcEndX}
        y={cy + 14}
        textAnchor="middle"
        fill="var(--color-text-muted)"
        fontSize="10"
        fontFamily="var(--font-body)"
      >
        Set
      </text>
    </svg>
  );
}

// --- Moon phase SVG ---

function MoonPhaseVis({ illumination, phase }: { illumination: number; phase: string }) {
  const r = 40;
  const cx = 50;
  const cy = 50;

  // Determine if the lit side is on the left or right.
  // Waxing = right side lit, waning = left side lit
  const isWaning = phase.toLowerCase().includes("waning") || phase.toLowerCase().includes("last");

  // The terminator curve: illumination 0 = new, 50 = quarter, 100 = full
  // We model this as an ellipse whose x-radius varies
  const frac = illumination / 100;
  // Shadow ellipse x-radius: at 0% -> same as r (full shadow), at 50% -> 0 (half), at 100% -> r (no shadow but flip)
  const shadowRx = Math.abs(1 - 2 * frac) * r;

  return (
    <svg
      viewBox="0 0 100 100"
      width="80"
      height="80"
      style={{ display: "block", margin: "0 auto" }}
    >
      {/* Lit circle */}
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="var(--color-solar-yellow)"
        opacity="0.9"
      />

      {/* Shadow overlay */}
      <ellipse
        cx={cx}
        cy={cy}
        rx={shadowRx}
        ry={r}
        fill="var(--color-bg-card-solid, var(--color-bg-card))"
      />

      {/* If waning, the shadow is on the right; if waxing, on the left.
          We use a clipping half to only show shadow on the correct side. */}
      {(() => {
        // For waxing: shadow is on the left side
        // For waning: shadow is on the right side
        const clipId = "moon-clip";
        // Determine which half should be dark
        const shouldDarkenRight = isWaning;

        // If illumination < 50, the shadow ellipse covers the lit side partially
        // We need a half-circle dark overlay + the terminator
        return (
          <>
            <defs>
              <clipPath id={clipId}>
                <rect
                  x={shouldDarkenRight ? cx : cx - r}
                  y={cy - r}
                  width={r}
                  height={r * 2}
                />
              </clipPath>
            </defs>
            {/* Dark half */}
            <circle
              cx={cx}
              cy={cy}
              r={r}
              fill="var(--color-bg-card-solid, var(--color-bg-card))"
              clipPath={`url(#${clipId})`}
            />
            {/* Terminator: either add light or dark ellipse depending on phase */}
            {frac < 0.5 ? (
              // Less than half lit: dark ellipse on the lit side
              <ellipse
                cx={cx}
                cy={cy}
                rx={shadowRx}
                ry={r}
                fill="var(--color-bg-card-solid, var(--color-bg-card))"
                clipPath={`url(#${clipId})`}
                style={{ transform: "none" }}
              />
            ) : (
              // More than half lit: light ellipse on the dark side
              <ellipse
                cx={cx}
                cy={cy}
                rx={shadowRx}
                ry={r}
                fill="var(--color-solar-yellow)"
                opacity="0.9"
                clipPath={`url(#${clipId})`}
              />
            )}
          </>
        );
      })()}

      {/* Subtle border */}
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="var(--color-border)"
        strokeWidth="0.5"
      />
    </svg>
  );
}

// --- Sun section ---

function SunSection({ sun }: { sun: SunData }) {
  const twilightRows = [
    {
      label: "Civil Twilight",
      dawn: sun.civil_twilight.dawn,
      dusk: sun.civil_twilight.dusk,
    },
    {
      label: "Nautical Twilight",
      dawn: sun.nautical_twilight.dawn,
      dusk: sun.nautical_twilight.dusk,
    },
    {
      label: "Astronomical Twilight",
      dawn: sun.astronomical_twilight.dawn,
      dusk: sun.astronomical_twilight.dusk,
    },
  ];

  // Determine if day_change is positive or negative for coloring
  const changeColor = useMemo(() => {
    if (sun.day_change.startsWith("+")) return "var(--color-success)";
    if (sun.day_change.startsWith("-")) return "var(--color-danger)";
    return "var(--color-text-secondary)";
  }, [sun.day_change]);

  return (
    <div style={cardStyle}>
      <h3 style={sectionTitle}>Sun</h3>

      {/* Sun arc visualization */}
      <SunArc sunrise={sun.sunrise} sunset={sun.sunset} />

      {/* Key data rows */}
      <div style={{ marginTop: "8px" }}>
        <div style={dataRow}>
          <span style={dataLabel}>Sunrise</span>
          <span style={dataValue}>{sun.sunrise}</span>
        </div>
        <div style={dataRow}>
          <span style={dataLabel}>Sunset</span>
          <span style={dataValue}>{sun.sunset}</span>
        </div>
        <div style={dataRow}>
          <span style={dataLabel}>Solar Noon</span>
          <span style={dataValue}>{sun.solar_noon}</span>
        </div>
        <div style={dataRow}>
          <span style={dataLabel}>Day Length</span>
          <span style={dataValue}>{sun.day_length}</span>
        </div>
        <div style={{ ...dataRow, borderBottom: "none" }}>
          <span style={dataLabel}>Daily Change</span>
          <span style={{ ...dataValue, color: changeColor }}>
            {sun.day_change}
          </span>
        </div>
      </div>

      {/* Twilight table */}
      <h4
        style={{
          margin: "20px 0 10px 0",
          fontSize: "15px",
          fontFamily: "var(--font-heading)",
          color: "var(--color-text-secondary)",
        }}
      >
        Twilight Times
      </h4>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr auto auto",
          gap: "0",
          fontSize: "13px",
          fontFamily: "var(--font-body)",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "8px 0",
            color: "var(--color-text-muted)",
            borderBottom: "1px solid var(--color-border)",
            fontWeight: 600,
          }}
        >
          Type
        </div>
        <div
          style={{
            padding: "8px 0 8px 24px",
            color: "var(--color-text-muted)",
            borderBottom: "1px solid var(--color-border)",
            fontWeight: 600,
            textAlign: "right",
          }}
        >
          Dawn
        </div>
        <div
          style={{
            padding: "8px 0 8px 24px",
            color: "var(--color-text-muted)",
            borderBottom: "1px solid var(--color-border)",
            fontWeight: 600,
            textAlign: "right",
          }}
        >
          Dusk
        </div>
        {twilightRows.map((row, idx) => (
          <div key={idx} style={{ display: "contents" }}>
            <div
              style={{
                padding: "8px 0",
                color: "var(--color-text-secondary)",
                borderBottom:
                  idx < twilightRows.length - 1
                    ? "1px solid var(--color-border-light)"
                    : "none",
              }}
            >
              {row.label}
            </div>
            <div
              style={{
                padding: "8px 0 8px 24px",
                color: "var(--color-text)",
                fontFamily: "var(--font-mono)",
                textAlign: "right",
                borderBottom:
                  idx < twilightRows.length - 1
                    ? "1px solid var(--color-border-light)"
                    : "none",
              }}
            >
              {row.dawn}
            </div>
            <div
              style={{
                padding: "8px 0 8px 24px",
                color: "var(--color-text)",
                fontFamily: "var(--font-mono)",
                textAlign: "right",
                borderBottom:
                  idx < twilightRows.length - 1
                    ? "1px solid var(--color-border-light)"
                    : "none",
              }}
            >
              {row.dusk}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Moon section ---

function MoonSection({ moon }: { moon: MoonData }) {
  return (
    <div style={cardStyle}>
      <h3 style={sectionTitle}>Moon</h3>

      {/* Moon phase visualization */}
      <MoonPhaseVis illumination={moon.illumination} phase={moon.phase} />

      {/* Phase name */}
      <div
        style={{
          textAlign: "center",
          margin: "12px 0 4px 0",
          fontSize: "16px",
          fontFamily: "var(--font-heading)",
          color: "var(--color-text)",
        }}
      >
        {moon.phase}
      </div>

      {/* Illumination bar */}
      <div style={{ margin: "12px 0 16px 0" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginBottom: "6px",
          }}
        >
          <span
            style={{
              color: "var(--color-text-secondary)",
              fontSize: "13px",
              fontFamily: "var(--font-body)",
            }}
          >
            Illumination
          </span>
          <span
            style={{
              fontSize: "13px",
              fontFamily: "var(--font-mono)",
              color: "var(--color-text-secondary)",
            }}
          >
            {moon.illumination}%
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
              width: `${Math.max(0, Math.min(100, moon.illumination))}%`,
              borderRadius: "4px",
              background: "var(--color-solar-yellow)",
              transition: "width 0.4s ease",
            }}
          />
        </div>
      </div>

      {/* Moon data rows */}
      <div style={dataRow}>
        <span style={dataLabel}>Next Full Moon</span>
        <span style={dataValue}>{moon.next_full}</span>
      </div>
      <div style={{ ...dataRow, borderBottom: "none" }}>
        <span style={dataLabel}>Next New Moon</span>
        <span style={dataValue}>{moon.next_new}</span>
      </div>
    </div>
  );
}

// --- Main component ---

export default function Astronomy() {
  const { astronomy } = useWeatherData();

  if (!astronomy) {
    return (
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
        <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
          <h2
            style={{
              margin: "0 0 16px 0",
              fontSize: "24px",
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            Astronomy
          </h2>
        </div>
        <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
        <div style={cardStyle}>
          <div style={emptyState}>
            Astronomy data is not yet available. Ensure the backend is running
            and a valid location is configured.
          </div>
        </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
        <h2
          style={{
            margin: "0 0 16px 0",
            fontSize: "24px",
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Astronomy
        </h2>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(340px, 100%), 1fr))",
          gap: "16px",
        }}
      >
        <SunSection sun={astronomy.sun} />
        <MoonSection moon={astronomy.moon} />
      </div>
      </div>
    </div>
  );
}

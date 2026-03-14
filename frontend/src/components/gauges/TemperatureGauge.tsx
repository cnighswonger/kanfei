/**
 * SVG vertical thermometer gauge with mercury fill and hi/lo whiskers.
 * Uses CSS custom properties for theming.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface TemperatureGaugeProps {
  value: number | null;       // Current temp in display units (e.g. 72.5)
  unit: string;               // 'F' or 'C'
  high?: number | null;       // Today's high
  low?: number | null;        // Today's low
  label?: string;             // e.g. 'Outside' or 'Inside'
  min?: number;               // Scale min (default: -20F or -30C)
  max?: number;               // Scale max (default: 120F or 50C)
}

const DEFAULT_RANGES = {
  F: { min: -20, max: 120 },
  C: { min: -30, max: 50 },
};

/** Compute a tight gauge range from the current value and daily hi/lo. */
function autoRange(
  value: number | null,
  high: number | null | undefined,
  low: number | null | undefined,
  unit: string,
): { min: number; max: number } {
  const defaults = DEFAULT_RANGES[unit as 'F' | 'C'] || DEFAULT_RANGES.F;
  const pts = [value, high ?? null, low ?? null].filter(
    (v): v is number => v != null && Number.isFinite(v),
  );
  if (pts.length === 0) return defaults;

  const dataMin = Math.min(...pts);
  const dataMax = Math.max(...pts);
  const PAD = unit === 'C' ? 8 : 15;
  const MIN_SPAN = unit === 'C' ? 20 : 30;
  const TICK = unit === 'C' ? 5 : 10;

  let lo = Math.floor((dataMin - PAD) / TICK) * TICK;
  let hi = Math.ceil((dataMax + PAD) / TICK) * TICK;

  // Ensure minimum span
  const span = hi - lo;
  if (span < MIN_SPAN) {
    const center = (lo + hi) / 2;
    lo = Math.floor((center - MIN_SPAN / 2) / TICK) * TICK;
    hi = Math.ceil((center + MIN_SPAN / 2) / TICK) * TICK;
  }

  // Clamp to physical limits
  lo = Math.max(defaults.min, lo);
  hi = Math.min(defaults.max, hi);

  return { min: lo, max: hi };
}

function tempColor(value: number, unit: string): string {
  // Map temperature to a color gradient: blue → green → red
  const range = DEFAULT_RANGES[unit as 'F' | 'C'] || DEFAULT_RANGES.F;
  const t = Math.max(0, Math.min(1, (value - range.min) / (range.max - range.min)));

  if (t < 0.35) {
    // Cold: blue to cyan
    const s = t / 0.35;
    return `rgb(${Math.round(30 + 0 * s)}, ${Math.round(100 + 155 * s)}, ${Math.round(220 - 20 * s)})`;
  } else if (t < 0.55) {
    // Cool to warm: cyan to green
    const s = (t - 0.35) / 0.2;
    return `rgb(${Math.round(30 + 100 * s)}, ${Math.round(200 - 10 * s)}, ${Math.round(100 - 60 * s)})`;
  } else {
    // Warm to hot: green to red
    const s = (t - 0.55) / 0.45;
    return `rgb(${Math.round(130 + 109 * s)}, ${Math.round(190 - 150 * s)}, ${Math.round(40 - 40 * s)})`;
  }
}

export default function TemperatureGauge({
  value,
  unit,
  high,
  low,
  label,
  min: customMin,
  max: customMax,
}: TemperatureGaugeProps) {
  const auto = autoRange(value, high, low, unit);
  const min = customMin ?? auto.min;
  const max = customMax ?? auto.max;

  // SVG dimensions
  const width = 100;
  const height = 280;
  const bulbCy = 245;
  const bulbR = 16;
  const tubeX = width / 2;
  const tubeTop = 30;
  const tubeBot = bulbCy - bulbR + 4;
  const tubeW = 10;

  const clamp = (v: number) => Math.max(min, Math.min(max, v));
  const yForTemp = (t: number) => {
    const frac = (clamp(t) - min) / (max - min);
    return tubeBot - frac * (tubeBot - tubeTop);
  };

  const displayVal = value !== null ? value : null;
  const mercuryY = displayVal !== null ? yForTemp(displayVal) : tubeBot;
  const fillColor = displayVal !== null ? tempColor(displayVal, unit) : 'var(--color-text-muted)';

  const isMobile = useCompact();
  if (isMobile) {
    return (
      <CompactCard
        label={label ?? "Temperature"}
        secondary={
          high != null || low != null ? (
            <span>H {high != null ? `${high.toFixed(0)}°` : "--"} / L {low != null ? `${low.toFixed(0)}°` : "--"}</span>
          ) : undefined
        }
      >
        <span style={{ fontSize: "28px", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: fillColor }}>
          {displayVal !== null ? `${displayVal.toFixed(1)}°${unit}` : "--.-°"}
        </span>
      </CompactCard>
    );
  }

  // Generate scale ticks
  const step = unit === 'C' ? 10 : 20;
  const ticks: number[] = [];
  for (let t = min; t <= max; t += step) {
    ticks.push(t);
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      padding: '12px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      boxShadow: 'var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))',
      border: '1px solid var(--color-border)',
      minWidth: '120px',
      height: '100%',
      boxSizing: 'border-box',
    }}>
      {label && (
        <div style={{
          fontSize: '12px',
          fontFamily: 'var(--font-body)',
          color: 'var(--color-text-secondary)',
          marginBottom: '4px',
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}>{label}</div>
      )}

      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <defs>
          <linearGradient id="mercuryGrad" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="var(--color-temp-cold, #3b82f6)" />
            <stop offset="50%" stopColor="var(--color-temp-mid, #22c55e)" />
            <stop offset="100%" stopColor="var(--color-temp-hot, #ef4444)" />
          </linearGradient>
          <clipPath id="tubeClip">
            <rect
              x={tubeX - tubeW / 2}
              y={tubeTop - 4}
              width={tubeW}
              height={tubeBot - tubeTop + 8}
              rx={tubeW / 2}
            />
            <circle cx={tubeX} cy={bulbCy} r={bulbR} />
          </clipPath>
        </defs>

        {/* Tube background */}
        <rect
          x={tubeX - tubeW / 2}
          y={tubeTop - 4}
          width={tubeW}
          height={tubeBot - tubeTop + 8}
          rx={tubeW / 2}
          fill="var(--color-gauge-track)"
          opacity="0.5"
        />

        {/* Bulb background */}
        <circle cx={tubeX} cy={bulbCy} r={bulbR} fill="var(--color-gauge-track)" opacity="0.5" />

        {/* Mercury fill */}
        <g clipPath="url(#tubeClip)">
          <rect
            x={tubeX - tubeW / 2 - 2}
            y={mercuryY}
            width={tubeW + 4}
            height={bulbCy + bulbR - mercuryY + 4}
            fill={fillColor}
            style={{ transition: 'y 0.8s ease, height 0.8s ease, fill 0.8s ease' }}
          />
        </g>

        {/* Scale ticks */}
        {ticks.map((t) => {
          const y = yForTemp(t);
          return (
            <g key={t}>
              <line
                x1={tubeX + tubeW / 2 + 4}
                y1={y}
                x2={tubeX + tubeW / 2 + 12}
                y2={y}
                stroke="var(--color-text-muted)"
                strokeWidth="1"
              />
              <text
                x={tubeX + tubeW / 2 + 16}
                y={y + 3}
                fontSize="9"
                fill="var(--color-text-secondary)"
                fontFamily="var(--font-gauge)"
              >
                {t}°
              </text>
            </g>
          );
        })}

        {/* High whisker */}
        {high != null && (
          <g>
            <line
              x1={tubeX - tubeW / 2 - 4}
              y1={yForTemp(high)}
              x2={tubeX - tubeW / 2 - 14}
              y2={yForTemp(high)}
              stroke="var(--color-temp-hot)"
              strokeWidth="2"
            />
            <text
              x={tubeX - tubeW / 2 - 17}
              y={yForTemp(high) + 3}
              fontSize="9"
              fill="var(--color-temp-hot)"
              fontFamily="var(--font-gauge)"
              textAnchor="end"
            >
              H {high.toFixed(0)}°
            </text>
          </g>
        )}

        {/* Low whisker */}
        {low != null && (
          <g>
            <line
              x1={tubeX - tubeW / 2 - 4}
              y1={yForTemp(low)}
              x2={tubeX - tubeW / 2 - 14}
              y2={yForTemp(low)}
              stroke="var(--color-temp-cold)"
              strokeWidth="2"
            />
            <text
              x={tubeX - tubeW / 2 - 17}
              y={yForTemp(low) + 3}
              fontSize="9"
              fill="var(--color-temp-cold)"
              fontFamily="var(--font-gauge)"
              textAnchor="end"
            >
              L {low.toFixed(0)}°
            </text>
          </g>
        )}
      </svg>

      {/* Digital readout */}
      <div style={{
        fontSize: '28px',
        fontFamily: 'var(--font-gauge)',
        fontWeight: 'bold',
        color: displayVal !== null ? fillColor : 'var(--color-text-muted)',
        marginTop: '-8px',
        transition: 'color 0.8s ease',
      }}>
        {displayVal !== null ? `${displayVal.toFixed(1)}°${unit}` : '--.-°'}
      </div>
    </div>
  );
}

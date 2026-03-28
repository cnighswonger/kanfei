/**
 * SVG semicircular arc gauge for humidity.
 * Yellow (dry) → Green (comfortable) → Blue (humid)
 * Scale dynamically adapts to current value and daily hi/lo.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface HumidityGaugeProps {
  value: number | null;  // 0-100%
  label?: string;        // 'Inside' or 'Outside'
  high?: number | null;  // Today's high
  low?: number | null;   // Today's low
}

/** Compute a tight gauge range from the current value and daily hi/lo. */
function autoRange(
  value: number | null,
  high: number | null | undefined,
  low: number | null | undefined,
): { min: number; max: number } {
  const pts = [value, high ?? null, low ?? null].filter(
    (v): v is number => v != null && Number.isFinite(v),
  );
  if (pts.length === 0) return { min: 0, max: 100 };

  const dataMin = Math.min(...pts);
  const dataMax = Math.max(...pts);
  const PAD = 10;
  const MIN_SPAN = 30;
  const TICK = 10;

  let lo = Math.floor((dataMin - PAD) / TICK) * TICK;
  let hi = Math.ceil((dataMax + PAD) / TICK) * TICK;

  // Ensure minimum span
  const span = hi - lo;
  if (span < MIN_SPAN) {
    const center = (lo + hi) / 2;
    lo = Math.floor((center - MIN_SPAN / 2) / TICK) * TICK;
    hi = Math.ceil((center + MIN_SPAN / 2) / TICK) * TICK;
  }

  // Clamp to physical limits (0-100%), then re-expand the other end
  // to maintain MIN_SPAN (avoids squished scale near 0% or 100%)
  lo = Math.max(0, lo);
  hi = Math.min(100, hi);
  if (hi - lo < MIN_SPAN) {
    if (lo === 0) hi = Math.min(100, MIN_SPAN);
    else if (hi === 100) lo = Math.max(0, 100 - MIN_SPAN);
  }

  return { min: lo, max: hi };
}

/** Generate tick values for the given range. */
function generateTicks(min: number, max: number): number[] {
  const span = max - min;
  const step = span <= 40 ? 5 : 10;
  const ticks: number[] = [];
  for (let t = min; t <= max; t += step) {
    ticks.push(t);
  }
  return ticks;
}

function humidityColor(pct: number): string {
  if (pct < 30) {
    // Dry: yellow-orange
    const t = pct / 30;
    return `rgb(${Math.round(230 - 30 * t)}, ${Math.round(180 + 20 * t)}, ${Math.round(40 + 20 * t)})`;
  } else if (pct < 60) {
    // Comfortable: green
    const t = (pct - 30) / 30;
    return `rgb(${Math.round(50 - 16 * t)}, ${Math.round(200 + 10 * t)}, ${Math.round(60 + 80 * t)})`;
  } else {
    // Humid: blue
    const t = (pct - 60) / 40;
    return `rgb(${Math.round(34 - 10 * t)}, ${Math.round(150 + 50 * t)}, ${Math.round(200 + 40 * t)})`;
  }
}

export default function HumidityGauge({ value, label, high, low }: HumidityGaugeProps) {
  const cx = 120;
  const cy = 120;
  const r = 90;
  const strokeWidth = 14;

  // Arc sweeps from left to right across the top (speedometer layout).
  // In our coordinate system (toRad shifts by -90°), 180° maps to the
  // bottom of the circle. We want left-to-right top arc, so use
  // standard SVG arc from (-r, cy) to (+r, cy) sweeping upward.
  const describeArc = (startFrac: number, endFrac: number, radius: number): string => {
    // Map fraction 0..1 to angle π..0 (left to right across top)
    const a1 = Math.PI * (1 - startFrac);
    const a2 = Math.PI * (1 - endFrac);
    const x1 = cx + radius * Math.cos(a1);
    const y1 = cy - radius * Math.sin(a1);
    const x2 = cx + radius * Math.cos(a2);
    const y2 = cy - radius * Math.sin(a2);
    const largeArc = (endFrac - startFrac) >= 0.5 ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 0 ${x2} ${y2}`;
  };

  const range = autoRange(value, high, low);
  const rangeSpan = range.max - range.min;
  const frac = value !== null
    ? Math.max(0, Math.min(0.998, (value - range.min) / rangeSpan))
    : 0;
  const color = value !== null ? humidityColor(value) : 'var(--color-text-muted)';

  // Helper: convert a 0..1 fraction to SVG coordinates on the arc
  const fracToXY = (f: number, radius: number) => {
    const angle = Math.PI * (1 - f);  // π (left) to 0 (right)
    return { x: cx + radius * Math.cos(angle), y: cy - radius * Math.sin(angle) };
  };

  const isMobile = useCompact();
  if (isMobile) {
    return (
      <CompactCard
        label={`${label ?? ""} Humidity`.trim()}
        secondary={
          high != null || low != null ? (
            <span>H {high ?? "--"}% / L {low ?? "--"}%</span>
          ) : undefined
        }
      >
        <span style={{ fontSize: "28px", fontFamily: "var(--font-gauge)", fontWeight: "bold", color }}>
          {value !== null ? `${value}%` : "--%"}
        </span>
      </CompactCard>
    );
  }

  const ticks = generateTicks(range.min, range.max);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '12px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      boxShadow: 'var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))',
      border: '1px solid var(--color-border)',
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
        }}>{label} Humidity</div>
      )}

      <svg width="240" height="145" viewBox="0 0 240 145">
        {/* Background arc (full semicircle) */}
        <path
          d={describeArc(0, 1, r)}
          fill="none"
          stroke="var(--color-gauge-track)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          opacity="0.4"
        />

        {/* Colored fill arc */}
        {value !== null && frac > 0.005 && (
          <path
            d={describeArc(0, frac, r)}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            style={{ transition: 'stroke 0.8s ease, d 0.8s ease' }}
          />
        )}

        {/* Tick marks */}
        {ticks.map((t) => {
          const tickFrac = (t - range.min) / rangeSpan;
          const inner = fracToXY(tickFrac, r - strokeWidth / 2 - 4);
          const outer = fracToXY(tickFrac, r - strokeWidth / 2 - 14);
          const labelPt = fracToXY(tickFrac, r - strokeWidth / 2 - 24);
          return (
            <g key={t}>
              <line
                x1={inner.x} y1={inner.y}
                x2={outer.x} y2={outer.y}
                stroke="var(--color-text-secondary)"
                strokeWidth="1.5"
              />
              <text
                x={labelPt.x} y={labelPt.y + 3}
                fontSize="10"
                fill="var(--color-text-secondary)"
                fontFamily="var(--font-gauge)"
                textAnchor="middle"
              >
                {t}
              </text>
            </g>
          );
        })}

        {/* Center value */}
        <text
          x={cx}
          y={cy + 5}
          fontSize="32"
          fontFamily="var(--font-gauge)"
          fontWeight="bold"
          fill={color}
          textAnchor="middle"
          style={{ transition: 'fill 0.8s ease' }}
        >
          {value !== null ? `${value}%` : '--%'}
        </text>
      </svg>

      {(high != null || low != null) && (
        <div style={{
          fontSize: '12px',
          fontFamily: 'var(--font-gauge)',
          color: 'var(--color-text-secondary)',
          marginTop: '-4px',
        }}>
          H {high != null ? `${high}%` : '--%'}
          {' / '}
          L {low != null ? `${low}%` : '--%'}
        </div>
      )}
    </div>
  );
}

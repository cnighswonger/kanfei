/**
 * SVG circular analog barometer dial with needle and trend arrow overlay.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface BarometerDialProps {
  value: number | null;        // Pressure in display units (e.g. 29.921 inHg)
  unit: string;                // 'inHg' or 'hPa'
  trend?: 'rising' | 'falling' | 'steady' | null;
  trendRate?: number | null;   // Rate of change
  high?: number | null;        // Today's high
  low?: number | null;         // Today's low
}

const RANGES = {
  inHg: { min: 28.5, max: 31.0, step: 0.5, decimals: 2 },
  hPa: { min: 965, max: 1050, step: 10, decimals: 0 },
};

export default function BarometerDial({ value, unit, trend, high, low }: BarometerDialProps) {
  const range = RANGES[unit as keyof typeof RANGES] || RANGES.inHg;
  const { min, max, step, decimals } = range;

  const cx = 130;
  const cy = 130;
  const r = 105;
  const startAngle = -225;  // degrees from 12 o'clock (bottom-left)
  const endAngle = 45;      // degrees (bottom-right)
  const sweep = endAngle - startAngle; // 270 degrees

  const valToAngle = (v: number): number => {
    const frac = Math.max(0, Math.min(1, (v - min) / (max - min)));
    return startAngle + frac * sweep;
  };

  const angleToXY = (angleDeg: number, radius: number) => {
    const rad = (angleDeg - 90) * (Math.PI / 180);
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  };

  // Generate tick marks
  const ticks: { value: number; major: boolean }[] = [];
  for (let v = min; v <= max; v += step) {
    ticks.push({ value: v, major: true });
    if (v + step / 2 <= max) {
      ticks.push({ value: v + step / 2, major: false });
    }
  }

  // Needle angle
  const needleAngle = value !== null ? valToAngle(value) : valToAngle((min + max) / 2);
  const needleTip = angleToXY(needleAngle, r - 15);
  const needleTail = angleToXY(needleAngle + 180, 12);

  // Zone labels
  const zones = unit === 'inHg'
    ? [
        { label: 'STORMY', angle: valToAngle(28.9) },
        { label: 'RAIN', angle: valToAngle(29.4) },
        { label: 'CHANGE', angle: valToAngle(29.75) },
        { label: 'FAIR', angle: valToAngle(30.1) },
        { label: 'DRY', angle: valToAngle(30.6) },
      ]
    : [
        { label: 'STORMY', angle: valToAngle(980) },
        { label: 'RAIN', angle: valToAngle(1000) },
        { label: 'CHANGE', angle: valToAngle(1013) },
        { label: 'FAIR', angle: valToAngle(1025) },
        { label: 'DRY', angle: valToAngle(1040) },
      ];

  const trendSymbol = trend === 'rising' ? '\u2191' : trend === 'falling' ? '\u2193' : trend === 'steady' ? '\u2192' : '';
  const trendColor = trend === 'rising' ? 'var(--color-success)' : trend === 'falling' ? 'var(--color-warning)' : 'var(--color-text-muted)';

  const isMobile = useCompact();
  if (isMobile) {
    return (
      <CompactCard
        label="Barometer"
        secondary={
          <>
            {trendSymbol && <span style={{ color: trendColor }}>{trendSymbol} </span>}
            {(high != null || low != null) && (
              <span>H {high?.toFixed(decimals) ?? "--"} / L {low?.toFixed(decimals) ?? "--"}</span>
            )}
          </>
        }
      >
        <span style={{ fontSize: "28px", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: "var(--color-text)" }}>
          {value !== null ? value.toFixed(decimals) : "--"}
        </span>
        <span style={{ fontSize: "12px", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
          {unit}
        </span>
      </CompactCard>
    );
  }

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
      <div style={{
        fontSize: '12px',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-text-secondary)',
        marginBottom: '4px',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
      }}>Barometer</div>

      <svg width="260" height="200" viewBox="0 0 260 200">
        {/* Dial face background */}
        <circle cx={cx} cy={cy} r={r + 8} fill="none" stroke="var(--color-border)" strokeWidth="1" />

        {/* Zone arc (colored background) */}
        {(() => {
          const arcStart = angleToXY(startAngle, r - 2);
          const arcEnd = angleToXY(endAngle, r - 2);
          const largeArc = sweep > 180 ? 1 : 0;
          return (
            <path
              d={`M ${arcStart.x} ${arcStart.y} A ${r - 2} ${r - 2} 0 ${largeArc} 1 ${arcEnd.x} ${arcEnd.y}`}
              fill="none"
              stroke="var(--color-gauge-track)"
              strokeWidth="20"
              opacity="0.4"
            />
          );
        })()}

        {/* Tick marks */}
        {ticks.map((tick, i) => {
          const angle = valToAngle(tick.value);
          const outerR = r + 2;
          const innerR = tick.major ? r - 18 : r - 10;
          const outer = angleToXY(angle, outerR);
          const inner = angleToXY(angle, innerR);
          const labelPos = angleToXY(angle, r - 28);
          return (
            <g key={i}>
              <line
                x1={outer.x} y1={outer.y}
                x2={inner.x} y2={inner.y}
                stroke="var(--color-text-secondary)"
                strokeWidth={tick.major ? 2 : 1}
              />
              {tick.major && (
                <text
                  x={labelPos.x} y={labelPos.y + 3}
                  fontSize="8"
                  fill="var(--color-text-muted)"
                  fontFamily="var(--font-gauge)"
                  textAnchor="middle"
                >
                  {tick.value.toFixed(unit === 'inHg' ? 1 : 0)}
                </text>
              )}
            </g>
          );
        })}

        {/* Zone labels */}
        {zones.map((zone, i) => {
          const pos = angleToXY(zone.angle, r - 45);
          return (
            <text
              key={i}
              x={pos.x} y={pos.y + 2}
              fontSize="6"
              fill="var(--color-text-muted)"
              fontFamily="var(--font-body)"
              textAnchor="middle"
              opacity="0.7"
            >
              {zone.label}
            </text>
          );
        })}

        {/* Needle */}
        <line
          x1={needleTail.x} y1={needleTail.y}
          x2={needleTip.x} y2={needleTip.y}
          stroke="var(--color-barometer-needle, #f59e0b)"
          strokeWidth="2.5"
          strokeLinecap="round"
          style={{ transition: 'x1 0.8s ease, y1 0.8s ease, x2 0.8s ease, y2 0.8s ease' }}
        />
        {/* Needle center */}
        <circle cx={cx} cy={cy} r="5" fill="var(--color-barometer-needle, #f59e0b)" />
        <circle cx={cx} cy={cy} r="2.5" fill="var(--color-bg-card-solid, var(--color-bg-card))" />

        {/* Digital readout at bottom of dial */}
        <text
          x={cx} y={cy + 35}
          fontSize="18"
          fontFamily="var(--font-gauge)"
          fontWeight="bold"
          fill="var(--color-text)"
          textAnchor="middle"
        >
          {value !== null ? value.toFixed(decimals) : '--'}
        </text>
        <text
          x={cx} y={cy + 48}
          fontSize="10"
          fontFamily="var(--font-body)"
          fill="var(--color-text-secondary)"
          textAnchor="middle"
        >
          {unit}
        </text>

        {/* Trend indicator */}
        {trend && (
          <text
            x={cx + 40} y={cy + 40}
            fontSize="20"
            fill={trend === 'rising' ? 'var(--color-success)' : trend === 'falling' ? 'var(--color-danger)' : 'var(--color-text-secondary)'}
            textAnchor="middle"
            fontWeight="bold"
          >
            {trendSymbol}
          </text>
        )}
      </svg>

      {(high != null || low != null) && (
        <div style={{
          fontSize: '12px',
          fontFamily: 'var(--font-gauge)',
          color: 'var(--color-text-secondary)',
          marginTop: '-4px',
        }}>
          H {high != null ? high.toFixed(decimals) : '--'}
          {' / '}
          L {low != null ? low.toFixed(decimals) : '--'}
        </div>
      )}
    </div>
  );
}

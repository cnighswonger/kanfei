/**
 * SVG semicircular arc gauge for humidity.
 * Yellow (dry) → Green (comfortable) → Blue (humid)
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface HumidityGaugeProps {
  value: number | null;  // 0-100%
  label?: string;        // 'Inside' or 'Outside'
  high?: number | null;  // Today's high
  low?: number | null;   // Today's low
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
  const cy = 115;
  const r = 90;
  const strokeWidth = 14;
  const startAngle = 180;
  const endAngle = 360;
  const sweep = endAngle - startAngle;

  const toRad = (deg: number) => (deg - 90) * (Math.PI / 180);

  const describeArc = (start: number, end: number, radius: number): string => {
    const startRad = toRad(start);
    const endRad = toRad(end);
    const x1 = cx + radius * Math.cos(startRad);
    const y1 = cy + radius * Math.sin(startRad);
    const x2 = cx + radius * Math.cos(endRad);
    const y2 = cy + radius * Math.sin(endRad);
    const largeArc = end - start >= 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  const frac = value !== null ? Math.max(0, Math.min(0.998, value / 100)) : 0;
  const fillAngle = startAngle + frac * sweep;
  const color = value !== null ? humidityColor(value) : 'var(--color-text-muted)';

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

  // Tick marks at 0, 20, 40, 60, 80, 100
  const ticks = [0, 20, 40, 60, 80, 100];

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
        {/* Background arc */}
        <path
          d={describeArc(startAngle, endAngle, r)}
          fill="none"
          stroke="var(--color-gauge-track)"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          opacity="0.4"
        />

        {/* Colored fill arc */}
        {value !== null && frac > 0.005 && (
          <path
            d={describeArc(startAngle, fillAngle, r)}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            style={{ transition: 'stroke 0.8s ease, d 0.8s ease' }}
          />
        )}

        {/* Tick marks */}
        {ticks.map((t) => {
          const angle = startAngle + (t / 100) * sweep;
          const rad = toRad(angle);
          const innerR = r - strokeWidth / 2 - 4;
          const outerR = r - strokeWidth / 2 - 14;
          return (
            <g key={t}>
              <line
                x1={cx + innerR * Math.cos(rad)}
                y1={cy + innerR * Math.sin(rad)}
                x2={cx + outerR * Math.cos(rad)}
                y2={cy + outerR * Math.sin(rad)}
                stroke="var(--color-text-muted)"
                strokeWidth="1"
              />
              <text
                x={cx + (outerR - 10) * Math.cos(rad)}
                y={cy + (outerR - 10) * Math.sin(rad) + 3}
                fontSize="9"
                fill="var(--color-text-muted)"
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

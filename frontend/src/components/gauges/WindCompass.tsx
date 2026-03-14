/**
 * SVG compass rose with direction arrow and speed display.
 * 16-point compass with animated direction arrow and speed in center.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface WindCompassProps {
  direction: number | null;  // 0-359 degrees
  speed: number | null;      // mph (or display unit)
  gust?: number | null;
  peak?: number | null;      // Today's peak wind speed
  unit: string;              // 'mph', 'kph', 'knots'
  cardinal?: string | null;  // e.g. 'NNE'
}

const CARDINALS_16 = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                       'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];

export default function WindCompass({ direction, speed, gust, peak, unit, cardinal }: WindCompassProps) {
  const isMobile = useCompact();
  if (isMobile) {
    return (
      <CompactCard
        label="Wind"
        secondary={
          <>
            <span>{cardinal ?? "--"}{direction != null ? ` ${direction}°` : ""}</span>
            {gust != null && <span style={{ color: "var(--color-warning)" }}> G {gust.toFixed(0)}</span>}
          </>
        }
      >
        <span style={{ fontSize: "28px", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: "var(--color-wind-arrow, #3b82f6)" }}>
          {speed !== null ? speed.toFixed(0) : "--"}
        </span>
        <span style={{ fontSize: "12px", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
          {unit}
        </span>
      </CompactCard>
    );
  }

  const cx = 130;
  const cy = 130;
  const outerR = 110;
  const innerR = 85;
  const arrowLen = 75;

  // Arrow rotation
  const arrowAngle = direction ?? 0;

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
      }}>Wind</div>

      <svg width="260" height="260" viewBox="0 0 260 260">
        {/* Outer ring */}
        <circle cx={cx} cy={cy} r={outerR} fill="none" stroke="var(--color-border)" strokeWidth="1.5" />
        <circle cx={cx} cy={cy} r={innerR} fill="none" stroke="var(--color-border)" strokeWidth="0.5" opacity="0.5" />

        {/* 16-point cardinal markers */}
        {CARDINALS_16.map((label, i) => {
          const angle = i * 22.5;
          const rad = (angle - 90) * (Math.PI / 180);
          const major = i % 4 === 0; // N, E, S, W
          const minor = i % 2 === 0; // NE, SE, SW, NW
          const tickOuter = outerR + 2;
          const tickInner = major ? outerR - 14 : minor ? outerR - 10 : outerR - 6;
          const labelR = outerR + 14;

          return (
            <g key={label}>
              <line
                x1={cx + tickInner * Math.cos(rad)}
                y1={cy + tickInner * Math.sin(rad)}
                x2={cx + tickOuter * Math.cos(rad)}
                y2={cy + tickOuter * Math.sin(rad)}
                stroke="var(--color-text-secondary)"
                strokeWidth={major ? 2 : 1}
              />
              {(major || minor) && (
                <text
                  x={cx + labelR * Math.cos(rad)}
                  y={cy + labelR * Math.sin(rad) + 3}
                  fontSize={major ? '12' : '8'}
                  fontFamily="var(--font-body)"
                  fontWeight={major ? 'bold' : 'normal'}
                  fill={major ? 'var(--color-text)' : 'var(--color-text-muted)'}
                  textAnchor="middle"
                >
                  {label}
                </text>
              )}
            </g>
          );
        })}

        {/* Direction arrow */}
        {direction !== null && (
          <g
            style={{
              transform: `rotate(${arrowAngle}deg)`,
              transformOrigin: `${cx}px ${cy}px`,
              transition: 'transform 0.8s ease',
            }}
          >
            {/* Arrow shaft */}
            <line
              x1={cx}
              y1={cy + 30}
              x2={cx}
              y2={cy - arrowLen}
              stroke="var(--color-wind-arrow, #3b82f6)"
              strokeWidth="3"
              strokeLinecap="round"
            />
            {/* Arrowhead */}
            <polygon
              points={`${cx},${cy - arrowLen - 8} ${cx - 7},${cy - arrowLen + 5} ${cx + 7},${cy - arrowLen + 5}`}
              fill="var(--color-wind-arrow, #3b82f6)"
            />
            {/* Tail */}
            <circle cx={cx} cy={cy + 30} r="3" fill="var(--color-wind-arrow, #3b82f6)" opacity="0.5" />
          </g>
        )}

        {/* Center hub */}
        <circle cx={cx} cy={cy} r="28" fill="var(--color-bg-card-solid, var(--color-bg-card))" stroke="var(--color-border)" strokeWidth="1" />

        {/* Speed in center */}
        <text
          x={cx}
          y={cy + 2}
          fontSize="22"
          fontFamily="var(--font-gauge)"
          fontWeight="bold"
          fill="var(--color-text)"
          textAnchor="middle"
          dominantBaseline="middle"
        >
          {speed !== null ? speed.toFixed(0) : '--'}
        </text>
        <text
          x={cx}
          y={cy + 16}
          fontSize="8"
          fontFamily="var(--font-body)"
          fill="var(--color-text-muted)"
          textAnchor="middle"
        >
          {unit}
        </text>
      </svg>

      {/* Bottom readout */}
      <div style={{
        display: 'flex',
        gap: '16px',
        fontSize: '13px',
        fontFamily: 'var(--font-gauge)',
        color: 'var(--color-text-secondary)',
        marginTop: '-4px',
      }}>
        <span>
          {cardinal ?? (direction !== null ? CARDINALS_16[Math.round(direction / 22.5) % 16] : '--')}
          {direction !== null ? ` ${direction}°` : ''}
        </span>
        {gust != null && (
          <span style={{ color: 'var(--color-warning)' }}>
            G {gust.toFixed(0)} {unit}
          </span>
        )}
        {peak != null && (
          <span>
            Peak {peak.toFixed(0)} {unit}
          </span>
        )}
      </div>
    </div>
  );
}

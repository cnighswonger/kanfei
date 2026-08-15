/**
 * Wind compass per Design REVIEW-02: 16-point compass from ``compass()``
 * with rose petals from ``rosePetals()`` inside the ring, needle overlay,
 * speed + cardinal read out to the right of the ring, gust/peak/bearing
 * on a footer rule.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";
import TileLabel from "../common/TileLabel.tsx";
import { formatTimestamp } from "../../utils/formatting.ts";
import { compass, rosePetals } from "../../utils/gauges.ts";

interface WindCompassProps {
  direction: number | null;
  speed: number | null;
  gust?: number | null;
  peak?: number | null;
  peakAt?: string | null;
  unit: string;
  cardinal?: string | null;
}

const CARDINALS_16 = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                       'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'];

// 220 px ring with compass(110, 110, 80, 98); petals fill outerR - 4.
const RING_SIZE = 220;

export default function WindCompass({ direction, speed, gust, peak, peakAt, unit, cardinal }: WindCompassProps) {
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
        <span style={{ fontSize: "calc(28px * var(--font-scale))", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: "var(--color-wind-arrow, #3b82f6)" }}>
          {speed !== null ? speed.toFixed(0) : "--"}
        </span>
        <span style={{ fontSize: "calc(12px * var(--font-scale))", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
          {unit}
        </span>
      </CompactCard>
    );
  }

  const cx = RING_SIZE / 2;
  const cy = RING_SIZE / 2;
  const outerR = 80;
  const labelR = 98;
  const petalMaxR = outerR - 4;

  const c = compass(cx, cy, outerR, labelR);
  // Decorative for now — passes no ``weights``, so ``rosePetals`` uses
  // its built-in demo distribution.  Wiring the live 4 h WindHistory
  // distribution is scope for the next composition PR; the petals are
  // a visual placeholder until then.
  const petals = rosePetals(cx, cy, petalMaxR);

  const arrowLen = outerR - 4;
  const arrowAngle = direction ?? 0;
  const derivedCardinal = cardinal ?? (direction != null ? CARDINALS_16[Math.round(direction / 22.5) % 16] : null);

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      padding: '16px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      boxShadow: 'var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))',
      border: '1px solid var(--color-border)',
      height: '100%',
      boxSizing: 'border-box',
      overflow: 'hidden',
    }}>
      <TileLabel>Wind</TileLabel>

      <div style={{ display: 'flex', flex: 1, minHeight: 0, alignItems: 'center', gap: '12px' }}>
        <svg
          width={RING_SIZE}
          height={RING_SIZE}
          viewBox={`0 0 ${RING_SIZE} ${RING_SIZE}`}
          style={{ flexShrink: 0, maxWidth: '100%', maxHeight: '100%' }}
        >
          {/* Rose petals under the compass ring */}
          {petals.map((p, i) => (
            <path key={`p${i}`} d={p.d} fill="var(--color-wind-arrow)" opacity={p.op} />
          ))}

          {/* Compass ticks */}
          {c.ticks.map((t, i) => (
            <line
              key={`t${i}`}
              x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
              stroke="var(--color-text-secondary)"
              strokeWidth={t.sw ?? 1}
            />
          ))}

          {/* Cardinal labels */}
          {c.labels.map((lbl, i) => (
            <text
              key={`l${i}`}
              x={lbl.x} y={lbl.y}
              fontFamily="var(--font-mono)"
              fontSize="calc(11px * var(--font-scale))"
              fill="var(--color-text)"
              textAnchor="middle"
            >
              {lbl.label}
            </text>
          ))}

          {/* Direction needle */}
          {direction != null && (
            <g
              style={{
                transform: `rotate(${arrowAngle}deg)`,
                transformOrigin: `${cx}px ${cy}px`,
                transition: 'transform 0.8s ease',
              }}
            >
              <line
                x1={cx} y1={cy}
                x2={cx} y2={cy - arrowLen}
                stroke="var(--color-wind-arrow)"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <polygon
                points={`${cx},${cy - arrowLen - 6} ${cx - 5},${cy - arrowLen + 3} ${cx + 5},${cy - arrowLen + 3}`}
                fill="var(--color-wind-arrow)"
              />
            </g>
          )}

          {/* Hub cap */}
          <circle cx={cx} cy={cy} r="4" fill="var(--color-wind-arrow)" />
          <circle cx={cx} cy={cy} r="1.5" fill="var(--color-bg-card)" />
        </svg>

        <div style={{
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minWidth: 0,
          gap: '6px',
        }}>
          <div>
            <span style={{
              fontFamily: 'var(--font-gauge)',
              fontSize: 'calc(34px * var(--font-scale))',
              fontWeight: 600,
              color: 'var(--color-text)',
            }}>
              {speed != null ? speed.toFixed(0) : '--'}
            </span>
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'calc(12px * var(--font-scale))',
              letterSpacing: '1.5px',
              textTransform: 'uppercase',
              color: 'var(--color-text-secondary)',
              marginLeft: '6px',
            }}>
              {unit} {derivedCardinal ?? ''}
            </span>
          </div>

          {(gust != null || peak != null) && (
            <div style={{
              fontFamily: 'var(--font-body)',
              fontSize: 'calc(11px * var(--font-scale))',
              color: 'var(--color-text-secondary)',
              lineHeight: 1.4,
            }}>
              {gust != null && <span>Gusting {gust.toFixed(0)}</span>}
              {gust != null && peak != null && '. '}
              {peak != null && <span>Peak {peak.toFixed(0)} {peakAt ? `at ${formatTimestamp(peakAt)}` : ''}</span>}
              {(gust != null || peak != null) && '.'}
            </div>
          )}

          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'calc(10px * var(--font-scale))',
            letterSpacing: '1px',
            color: 'var(--color-text-muted)',
            marginTop: 'auto',
            paddingTop: '8px',
            borderTop: `var(--rule-width, 1px) var(--rule-style, solid) var(--rule-hair)`,
          }}>
            {direction != null ? `${direction}°` : '--'}
          </div>
        </div>
      </div>
    </div>
  );
}

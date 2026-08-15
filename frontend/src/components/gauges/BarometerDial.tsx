/**
 * Wheel barometer per Design REVIEW-02: 240° sweep aneroid dial from
 * ``wheelDial()`` at 300 px on desktop, graduated ticks + zone names +
 * a pale 3 h-old trend hand.  Value / trend / zone / H·L readout sits
 * beside the dial (portrait tile) or below (very-narrow fallback).
 */
import { useTheme } from "../../context/ThemeContext.tsx";
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";
import TileLabel from "../common/TileLabel.tsx";
import { formatTimestamp } from "../../utils/formatting.ts";
import { wheelDial, DEFAULT_DIAL } from "../../utils/gauges.ts";

interface BarometerDialProps {
  value: number | null;
  unit: string;
  trend?: 'rising' | 'falling' | 'steady' | null;
  trendRate?: number | null;
  high?: number | null;
  low?: number | null;
  highAt?: string | null;
  lowAt?: string | null;
}

const DIAL_SIZE = 300;

function zoneFor(inHg: number): string {
  if (inHg < 28.9) return 'stormy';
  if (inHg < 29.4) return 'rain';
  if (inHg < 29.9) return 'change';
  if (inHg < 30.4) return 'fair';
  return 'set fair';
}

export default function BarometerDial({
  value, unit, trend, trendRate, high, low, highAt, lowAt,
}: BarometerDialProps) {
  const isMobile = useCompact();
  const { theme } = useTheme();

  const decimals = unit === 'inHg' ? 2 : 0;
  const trendSymbol = trend === 'rising' ? '↑' : trend === 'falling' ? '↓' : trend === 'steady' ? '→' : '';
  const trendLabel = trend === 'rising' ? 'RISING' : trend === 'falling' ? 'FALLING' : trend === 'steady' ? 'STEADY' : '';

  if (isMobile) {
    return (
      <CompactCard
        label="Barometer"
        secondary={
          <>
            {trendSymbol && <span>{trendSymbol} </span>}
            {(high != null || low != null) && (
              <span>H {high?.toFixed(decimals) ?? "--"} / L {low?.toFixed(decimals) ?? "--"}</span>
            )}
          </>
        }
      >
        <span style={{ fontSize: "calc(28px * var(--font-scale))", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: "var(--color-text)" }}>
          {value !== null ? value.toFixed(decimals) : "--"}
        </span>
        <span style={{ fontSize: "calc(12px * var(--font-scale))", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
          {unit}
        </span>
      </CompactCard>
    );
  }

  // wheelDial's fixed range is inHg (28.5–31.0); pass through when unit
  // matches, fall back to dial-midpoint when the value is null.
  const dialValue = value ?? 29.92;
  const d = wheelDial(dialValue, DIAL_SIZE, theme.dial ?? DEFAULT_DIAL);
  const rimStroke = 'var(--color-border)';
  const ink = 'var(--color-text)';
  const inkSecondary = 'var(--color-text-secondary)';
  const inkMuted = 'var(--color-text-muted)';
  const needleColor = 'var(--color-barometer-needle)';

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
      <TileLabel>Barometer</TileLabel>

      <div style={{ display: 'flex', flex: 1, minHeight: 0, alignItems: 'center', gap: '12px' }}>
        <svg
          width={DIAL_SIZE}
          height={DIAL_SIZE}
          viewBox={`0 0 ${DIAL_SIZE} ${DIAL_SIZE}`}
          style={{ flexShrink: 0, maxWidth: '100%', maxHeight: '100%' }}
        >
          {/* Rim pair */}
          <circle cx={d.cx} cy={d.cy} r={d.rimOuter} fill="none" stroke={rimStroke} strokeWidth="1" />
          <circle cx={d.cx} cy={d.cy} r={d.rimInner} fill="none" stroke={rimStroke} strokeWidth="0.5" opacity="0.6" />

          {/* Minor ticks then major (render order per gauges.ts docstring) */}
          {d.minor.map((t, i) => (
            <line key={`m${i}`} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} stroke={inkSecondary} strokeWidth={t.sw ?? 1} />
          ))}
          {d.major.map((t, i) => (
            <line key={`M${i}`} x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2} stroke={ink} strokeWidth={t.sw ?? 2} />
          ))}

          {/* Numerals */}
          {d.numerals.map((n, i) => (
            <text
              key={`n${i}`}
              x={n.x} y={n.y}
              fontFamily="var(--font-gauge)"
              fontSize="calc(11px * var(--font-scale))"
              fill={ink}
              textAnchor="middle"
            >
              {n.label}
            </text>
          ))}

          {/* Zone words */}
          {d.zones.map((z, i) => (
            <text
              key={`z${i}`}
              x={z.x} y={z.y}
              fontFamily="var(--font-mono)"
              fontSize="calc(9px * var(--font-scale))"
              letterSpacing="1.2"
              fill={inkMuted}
              textAnchor="middle"
            >
              {z.label}
            </text>
          ))}

          {/* Trend hand (pale, 3 h behind) */}
          <line
            x1={d.cx} y1={d.cy}
            x2={d.trend.x} y2={d.trend.y}
            stroke={needleColor}
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.35"
          />

          {/* Live needle */}
          <line
            x1={d.cx} y1={d.cy}
            x2={d.tip.x} y2={d.tip.y}
            stroke={needleColor}
            strokeWidth="2.5"
            strokeLinecap="round"
            style={{ transition: 'x2 0.8s ease, y2 0.8s ease' }}
          />

          {/* Hub cap */}
          <circle cx={d.cx} cy={d.cy} r="5" fill={needleColor} />
          <circle cx={d.cx} cy={d.cy} r="2" fill="var(--color-bg-card)" />
        </svg>

        <div style={{
          display: 'flex',
          flexDirection: 'column',
          flex: 1,
          minWidth: 0,
          gap: '10px',
        }}>
          <div>
            <span style={{
              fontFamily: 'var(--font-gauge)',
              fontSize: 'calc(34px * var(--font-scale))',
              fontWeight: 600,
              color: ink,
            }}>
              {value != null ? value.toFixed(decimals) : '--'}
            </span>
            <span style={{
              fontFamily: 'var(--font-gauge)',
              fontSize: 'calc(13px * var(--font-scale))',
              color: inkMuted,
              marginLeft: '4px',
            }}>
              {unit}
            </span>
          </div>

          {trendLabel && (
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 'calc(10px * var(--font-scale))',
              letterSpacing: '1.5px',
              textTransform: 'uppercase',
              color: inkSecondary,
            }}>
              {trendSymbol} {trendLabel}
              {trendRate != null && ` ${trendRate >= 0 ? '+' : ''}${trendRate.toFixed(2)} ${unit.toUpperCase()}/3H`}
            </div>
          )}

          <div style={{
            fontFamily: 'var(--font-body)',
            fontSize: 'calc(11px * var(--font-scale))',
            fontStyle: 'italic',
            color: inkSecondary,
            lineHeight: 1.4,
          }}>
            Zone: {zoneFor(value ?? 29.92)}.
          </div>

          {(high != null || low != null) && (
            <div style={{
              fontFamily: 'var(--font-gauge)',
              fontSize: 'calc(11px * var(--font-scale))',
              color: inkSecondary,
              marginTop: 'auto',
              paddingTop: '8px',
              borderTop: `var(--rule-width, 1px) var(--rule-style, solid) var(--rule-hair)`,
            }}>
              <div>
                H {high != null ? high.toFixed(decimals) : '--'} · L {low != null ? low.toFixed(decimals) : '--'}
              </div>
              {(highAt || lowAt) && (
                <div style={{ fontSize: 'calc(10px * var(--font-scale))', color: inkMuted, marginTop: '2px' }}>
                  {highAt && `H ${formatTimestamp(highAt)}`}
                  {highAt && lowAt && ' · '}
                  {lowAt && `L ${formatTimestamp(lowAt)}`}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

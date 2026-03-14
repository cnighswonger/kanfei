/**
 * Combined Solar Radiation and UV Index gauge.
 * Only shown when the station supports solar/UV sensors.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface SolarUVGaugeProps {
  solarRadiation: number | null;  // W/m2
  uvIndex: number | null;         // UV index (e.g. 5.2)
}

function uvColor(uv: number): string {
  if (uv < 3) return '#22c55e';     // Low - green
  if (uv < 6) return '#f59e0b';     // Moderate - yellow
  if (uv < 8) return '#f97316';     // High - orange
  if (uv < 11) return '#ef4444';    // Very high - red
  return '#7c3aed';                  // Extreme - purple
}

function uvLabel(uv: number): string {
  if (uv < 3) return 'Low';
  if (uv < 6) return 'Moderate';
  if (uv < 8) return 'High';
  if (uv < 11) return 'Very High';
  return 'Extreme';
}

function solarIntensity(wr: number): { label: string; color: string } {
  if (wr === 0) return { label: 'None', color: 'var(--color-text-muted)' };
  if (wr < 200) return { label: 'Low', color: '#f59e0b' };
  if (wr < 600) return { label: 'Moderate', color: '#f97316' };
  if (wr < 1000) return { label: 'High', color: '#ef4444' };
  return { label: 'Very High', color: '#dc2626' };
}

export default function SolarUVGauge({ solarRadiation, uvIndex }: SolarUVGaugeProps) {
  // UV arc gauge parameters
  const cx = 100;
  const cy = 60;
  const r = 45;
  const arcStroke = 10;
  const startAngle = 180;
  const endAngle = 360;
  const sweep = endAngle - startAngle;
  const maxUV = 14;

  const toRad = (deg: number) => (deg - 90) * (Math.PI / 180);
  const describeArc = (start: number, end: number, radius: number) => {
    const sr = toRad(start);
    const er = toRad(end);
    const x1 = cx + radius * Math.cos(sr);
    const y1 = cy + radius * Math.sin(sr);
    const x2 = cx + radius * Math.cos(er);
    const y2 = cy + radius * Math.sin(er);
    const la = end - start >= 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${radius} ${radius} 0 ${la} 1 ${x2} ${y2}`;
  };

  const uvFrac = uvIndex !== null ? Math.min(uvIndex / maxUV, 0.998) : 0;
  const uvFillAngle = startAngle + uvFrac * sweep;
  const uvCol = uvIndex !== null ? uvColor(uvIndex) : 'var(--color-text-muted)';
  const solar = solarRadiation !== null ? solarIntensity(solarRadiation) : null;

  const isMobile = useCompact();
  if (isMobile) {
    return (
      <CompactCard
        label="Solar & UV"
        secondary={
          <span>Solar: {solarRadiation !== null ? `${solarRadiation} W/m\u00B2` : "--"}</span>
        }
      >
        <span style={{ fontSize: "28px", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: uvCol }}>
          {uvIndex !== null ? uvIndex.toFixed(1) : "--"}
        </span>
        <span style={{ fontSize: "12px", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
          UV
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
      padding: '16px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      boxShadow: 'var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))',
      border: '1px solid var(--color-border)',
      minWidth: '160px',
      height: '100%',
      boxSizing: 'border-box',
    }}>
      {/* UV Index section */}
      <div style={{
        fontSize: '12px',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '4px',
      }}>UV Index</div>

      <svg width="200" height="80" viewBox="0 0 200 80">
        {/* Background arc */}
        <path
          d={describeArc(startAngle, endAngle, r)}
          fill="none"
          stroke="var(--color-gauge-track)"
          strokeWidth={arcStroke}
          strokeLinecap="round"
          opacity="0.4"
        />

        {/* Fill arc */}
        {uvIndex !== null && uvFrac > 0.01 && (
          <path
            d={describeArc(startAngle, uvFillAngle, r)}
            fill="none"
            stroke={uvCol}
            strokeWidth={arcStroke}
            strokeLinecap="round"
            style={{ transition: 'stroke 0.6s ease' }}
          />
        )}

        {/* Center value */}
        <text
          x={cx}
          y={cy + 5}
          fontSize="24"
          fontFamily="var(--font-gauge)"
          fontWeight="bold"
          fill={uvCol}
          textAnchor="middle"
          style={{ transition: 'fill 0.6s ease' }}
        >
          {uvIndex !== null ? uvIndex.toFixed(1) : '--'}
        </text>
      </svg>

      <div style={{
        fontSize: '11px',
        fontFamily: 'var(--font-body)',
        color: uvCol,
        fontWeight: 'bold',
        marginTop: '-4px',
        marginBottom: '12px',
      }}>
        {uvIndex !== null ? uvLabel(uvIndex) : 'No data'}
      </div>

      {/* Divider */}
      <div style={{
        width: '80%',
        height: '1px',
        background: 'var(--color-border)',
        marginBottom: '12px',
      }} />

      {/* Solar Radiation section */}
      <div style={{
        fontSize: '12px',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
      }}>Solar Radiation</div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
        <span style={{
          fontSize: '28px',
          fontFamily: 'var(--font-gauge)',
          fontWeight: 'bold',
          color: solar?.color ?? 'var(--color-text-muted)',
          transition: 'color 0.5s ease',
        }}>
          {solarRadiation !== null ? solarRadiation : '--'}
        </span>
        <span style={{
          fontSize: '12px',
          fontFamily: 'var(--font-body)',
          color: 'var(--color-text-muted)',
        }}>
          W/m²
        </span>
      </div>

      <div style={{
        fontSize: '11px',
        fontFamily: 'var(--font-body)',
        color: solar?.color ?? 'var(--color-text-muted)',
        fontWeight: 'bold',
      }}>
        {solar?.label ?? 'No data'}
      </div>
    </div>
  );
}

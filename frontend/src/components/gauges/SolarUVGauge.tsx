/**
 * Combined Solar Radiation and UV Index gauge.
 * Only shown when the station supports solar/UV sensors.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface ValueWithUnit {
  value: number;
  unit: string;
}

interface SolarUVGaugeProps {
  solarRadiation: number | null;                   // W/m²
  uvIndex: number | null;                          // UV index (e.g. 5.2)
  uvWarning?: string | null;                       // WHO band, from server
  solarEnergyDaily?: ValueWithUnit | null;         // today's cumulative (MJ/m², kWh/m², or Wh/m²)
  etDaily?: ValueWithUnit | null;                  // today's evapotranspiration
  etMonthly?: ValueWithUnit | null;                // this month's ET
  etYearly?: ValueWithUnit | null;                 // this year's ET
}

function uvColor(uv: number): string {
  if (uv < 3) return 'var(--color-uv-low, var(--color-success, #22c55e))';
  if (uv < 6) return 'var(--color-uv-moderate, var(--color-warning, #f59e0b))';
  if (uv < 8) return 'var(--color-uv-high, #f97316)';
  if (uv < 11) return 'var(--color-uv-very-high, var(--color-danger, #ef4444))';
  return 'var(--color-uv-extreme, #7c3aed)';
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
  if (wr < 200) return { label: 'Low', color: 'var(--color-solar-low, var(--color-solar-yellow, #f59e0b))' };
  if (wr < 600) return { label: 'Moderate', color: 'var(--color-solar-moderate, #f97316)' };
  if (wr < 1000) return { label: 'High', color: 'var(--color-solar-high, var(--color-danger, #ef4444))' };
  return { label: 'Very High', color: 'var(--color-solar-extreme, #dc2626)' };
}

function formatEnergyValue(v: ValueWithUnit | null | undefined): string {
  if (v == null) return "--";
  // MJ/m² and kWh/m² read best with one decimal for the low end of the range;
  // Wh/m² is already a whole-number quantity. joules_to_display_unit already
  // rounded server-side, but we render in a consistent shape here.
  const decimals = v.unit === "Wh/m²" ? 0 : v.unit === "kWh/m²" ? 2 : 2;
  return v.value.toFixed(decimals);
}

function formatEtValue(v: ValueWithUnit | null | undefined): string {
  if (v == null) return "--";
  // Inches want more precision (typical daily ET is < 0.3 in); mm wants less.
  return v.unit === "mm" ? v.value.toFixed(1) : v.value.toFixed(3);
}

export default function SolarUVGauge({
  solarRadiation,
  uvIndex,
  uvWarning,
  solarEnergyDaily,
  etDaily,
  etMonthly,
  etYearly,
}: SolarUVGaugeProps) {
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
          <span>
            {uvIndex !== null && (
              <span style={{ color: uvCol, fontWeight: 600 }}>
                {uvWarning ?? uvLabel(uvIndex)}
              </span>
            )}
            {uvIndex !== null && ' \u00B7 '}
            Solar: {solarRadiation !== null ? `${solarRadiation} W/m\u00B2` : "--"}
          </span>
        }
      >
        <span style={{ fontSize: "calc(28px * var(--font-scale))", fontFamily: "var(--font-gauge)", fontWeight: "bold", color: uvCol }}>
          {uvIndex !== null ? uvIndex.toFixed(1) : "--"}
        </span>
        <span style={{ fontSize: "calc(12px * var(--font-scale))", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
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
        fontSize: 'calc(12px * var(--font-scale))',
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
          style={{ fontSize: "calc(24px * var(--font-scale))", transition: 'fill 0.6s ease' }}
          fontFamily="var(--font-gauge)"
          fontWeight="bold"
          fill={uvCol}
          textAnchor="middle"
        >
          {uvIndex !== null ? uvIndex.toFixed(1) : '--'}
        </text>
      </svg>

      <div style={{
        fontSize: 'calc(11px * var(--font-scale))',
        fontFamily: 'var(--font-body)',
        color: uvCol,
        fontWeight: 'bold',
        marginTop: '-4px',
        marginBottom: '12px',
      }}>
        {uvIndex !== null ? (uvWarning ?? uvLabel(uvIndex)) : 'No data'}
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
        fontSize: 'calc(12px * var(--font-scale))',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
      }}>Solar Radiation</div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
        <span style={{
          fontSize: 'calc(28px * var(--font-scale))',
          fontFamily: 'var(--font-gauge)',
          fontWeight: 'bold',
          color: solar?.color ?? 'var(--color-text-muted)',
          transition: 'color 0.5s ease',
        }}>
          {solarRadiation !== null ? solarRadiation : '--'}
        </span>
        <span style={{
          fontSize: 'calc(12px * var(--font-scale))',
          fontFamily: 'var(--font-body)',
          color: 'var(--color-text-muted)',
        }}>
          W/m²
        </span>
      </div>

      <div style={{
        fontSize: 'calc(11px * var(--font-scale))',
        fontFamily: 'var(--font-body)',
        color: solar?.color ?? 'var(--color-text-muted)',
        fontWeight: 'bold',
      }}>
        {solar?.label ?? 'No data'}
      </div>

      {/* Cumulative daily solar energy — trapezoid-integrated since local
          midnight, unit picked by the operator (MJ/m², kWh/m², Wh/m²).
          Hidden entirely when the station has no solar sensor or fewer
          than two samples have landed yet. */}
      {solarEnergyDaily != null && (
        <div style={{
          marginTop: '10px',
          fontSize: 'calc(11px * var(--font-scale))',
          fontFamily: 'var(--font-body)',
          color: 'var(--color-text-muted)',
          textAlign: 'center',
        }}>
          Today: <span style={{
            color: 'var(--color-text)',
            fontFamily: 'var(--font-gauge)',
            fontWeight: 600,
          }}>{formatEnergyValue(solarEnergyDaily)}</span> {solarEnergyDaily.unit}
        </div>
      )}

      {/* Evapotranspiration — Day / Month / Year totals reported directly
          by the console. Hidden entirely when the driver doesn't report
          ET (needs solar + temp/humidity/wind on the station side). */}
      {(etDaily != null || etMonthly != null || etYearly != null) && (
        <>
          <div style={{
            width: '80%',
            height: '1px',
            background: 'var(--color-border)',
            marginTop: '12px',
            marginBottom: '10px',
          }} />
          <div style={{
            fontSize: 'calc(12px * var(--font-scale))',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-text-secondary)',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            marginBottom: '6px',
          }}>Evapotranspiration</div>
          <table style={{
            fontSize: 'calc(11px * var(--font-scale))',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-text)',
            borderCollapse: 'collapse',
          }}>
            <tbody>
              {etDaily != null && (
                <tr>
                  <td style={{ paddingRight: '10px', opacity: 0.75 }}>Today</td>
                  <td style={{ fontFamily: 'var(--font-gauge)', fontWeight: 600, textAlign: 'right' }}>
                    {formatEtValue(etDaily)}
                  </td>
                  <td style={{ paddingLeft: '4px', opacity: 0.75 }}>{etDaily.unit}</td>
                </tr>
              )}
              {etMonthly != null && (
                <tr>
                  <td style={{ paddingRight: '10px', opacity: 0.75 }}>Month</td>
                  <td style={{ fontFamily: 'var(--font-gauge)', fontWeight: 600, textAlign: 'right' }}>
                    {formatEtValue(etMonthly)}
                  </td>
                  <td style={{ paddingLeft: '4px', opacity: 0.75 }}>{etMonthly.unit}</td>
                </tr>
              )}
              {etYearly != null && (
                <tr>
                  <td style={{ paddingRight: '10px', opacity: 0.75 }}>Year</td>
                  <td style={{ fontFamily: 'var(--font-gauge)', fontWeight: 600, textAlign: 'right' }}>
                    {formatEtValue(etYearly)}
                  </td>
                  <td style={{ paddingLeft: '4px', opacity: 0.75 }}>{etYearly.unit}</td>
                </tr>
              )}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

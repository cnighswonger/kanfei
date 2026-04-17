/**
 * Rain display: current rate + daily/yesterday/yearly totals as a compact numeric panel.
 */
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

interface RainGaugeProps {
  rate: number | null;       // inches/hr (or display unit per hr)
  daily: number | null;      // daily accumulation
  yesterday: number | null;  // yesterday's total (midnight auto-reset)
  yearly: number | null;     // yearly total
  unit: string;              // 'in' or 'mm'
  peakRate?: number | null;  // Today's peak rain rate
}

function rateColor(rate: number): string {
  if (rate === 0) return 'var(--color-text-muted)';
  if (rate < 0.1) return 'var(--color-rain-blue, #06b6d4)';
  if (rate < 0.3) return 'var(--color-rain-moderate, #0ea5e9)';
  if (rate < 1.0) return 'var(--color-rain-heavy, #2563eb)';
  return 'var(--color-rain-extreme, #7c3aed)';
}

export default function RainGauge({ rate, daily, yesterday, yearly, unit, peakRate }: RainGaugeProps) {
  const decimals = unit === 'mm' ? 1 : 2;
  const rateStr = rate !== null ? rate.toFixed(decimals) : '--';
  const dailyStr = daily !== null ? daily.toFixed(decimals) : '--';
  const yesterdayStr = yesterday !== null ? yesterday.toFixed(decimals) : '--';
  const yearlyStr = yearly !== null ? yearly.toFixed(decimals) : '--';

  const color = rate !== null ? rateColor(rate) : 'var(--color-text-muted)';

  const isMobile = useCompact();
  if (isMobile) {
    return (
      <CompactCard
        label="Rain"
        secondary={<span>Day {dailyStr} / Yest {yesterdayStr} / Yr {yearlyStr}</span>}
      >
        <span style={{ fontSize: "28px", fontFamily: "var(--font-gauge)", fontWeight: "bold", color }}>
          {rateStr}
        </span>
        <span style={{ fontSize: "12px", fontFamily: "var(--font-gauge)", color: "var(--color-text-muted)", marginLeft: "2px" }}>
          {unit}/hr
        </span>
      </CompactCard>
    );
  }

  // Animated rain drops for active rain
  const isRaining = rate !== null && rate > 0;

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
      <div style={{
        fontSize: '12px',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-text-secondary)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
      }}>Rain</div>

      {/* Rain rate - large display */}
      <div style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: '4px',
        marginBottom: '4px',
      }}>
        <svg width="24" height="24" viewBox="0 0 24 24" style={{ opacity: isRaining ? 1 : 0.3 }}>
          <path
            d="M12 2C12 2 5 11 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 11 12 2 12 2Z"
            fill={color}
            opacity="0.8"
          />
        </svg>
        <span style={{
          fontSize: '36px',
          fontFamily: 'var(--font-gauge)',
          fontWeight: 'bold',
          color: color,
          lineHeight: '1',
          transition: 'color 0.5s ease',
        }}>
          {rateStr}
        </span>
        <span style={{
          fontSize: '12px',
          fontFamily: 'var(--font-body)',
          color: 'var(--color-text-muted)',
        }}>
          {unit}/hr
        </span>
      </div>

      {/* Rain status text */}
      <div style={{
        fontSize: '11px',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-text-muted)',
        marginBottom: '12px',
      }}>
        {rate === null ? 'No data' :
         rate === 0 ? 'Not raining' :
         rate < 0.1 ? 'Light rain' :
         rate < 0.3 ? 'Moderate rain' :
         rate < 1.0 ? 'Heavy rain' : 'Very heavy rain'}
      </div>

      {peakRate != null && peakRate > 0 && (
        <div style={{
          fontSize: '11px',
          fontFamily: 'var(--font-body)',
          color: 'var(--color-text-secondary)',
          marginBottom: '4px',
        }}>
          Peak: {peakRate.toFixed(decimals)} {unit}/hr
        </div>
      )}

      {/* Divider */}
      <div style={{
        width: '80%',
        height: '1px',
        background: 'var(--color-border)',
        marginBottom: '12px',
      }} />

      {/* Totals */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        gap: '8px',
        width: '100%',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontSize: '10px',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-text-muted)',
            textTransform: 'uppercase',
            marginBottom: '2px',
          }}>Today</div>
          <div style={{
            fontSize: '18px',
            fontFamily: 'var(--font-gauge)',
            fontWeight: 'bold',
            color: 'var(--color-text)',
          }}>
            {dailyStr}
          </div>
          <div style={{
            fontSize: '10px',
            color: 'var(--color-text-muted)',
          }}>{unit}</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontSize: '10px',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-text-muted)',
            textTransform: 'uppercase',
            marginBottom: '2px',
          }}>Yesterday</div>
          <div style={{
            fontSize: '18px',
            fontFamily: 'var(--font-gauge)',
            fontWeight: 'bold',
            color: 'var(--color-text)',
          }}>
            {yesterdayStr}
          </div>
          <div style={{
            fontSize: '10px',
            color: 'var(--color-text-muted)',
          }}>{unit}</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontSize: '10px',
            fontFamily: 'var(--font-body)',
            color: 'var(--color-text-muted)',
            textTransform: 'uppercase',
            marginBottom: '2px',
          }}>Year</div>
          <div style={{
            fontSize: '18px',
            fontFamily: 'var(--font-gauge)',
            fontWeight: 'bold',
            color: 'var(--color-text)',
          }}>
            {yearlyStr}
          </div>
          <div style={{
            fontSize: '10px',
            color: 'var(--color-text-muted)',
          }}>{unit}</div>
        </div>
      </div>
    </div>
  );
}

/**
 * Hero outside-air tile per Design REVIEW-02.
 *
 * The outside temperature is the anchor of the whole dashboard, and
 * the mock treats it typographically, not as a gauge: big italic-serif
 * numeral in ``type.display`` (104px on paper themes), Zambretti
 * sentence in italic serif below with a mono-caps confidence footer,
 * then two bordered H/L chips at the bottom.
 *
 * Replaces the vertical thermometer for outside-temp — Design's note:
 * "the vertical thermometer bar isn't in the mock at all… it's the one
 * metric that doesn't need a gauge, because the number IS the reading."
 * TemperatureGauge stays around for inside-temp, which the user can
 * still add from the tile catalog.
 */
import { useEffect, useState } from 'react';
import { useWeatherData } from '../../context/WeatherDataContext.tsx';
import { useCompact } from '../../dashboard/CompactContext.tsx';
import CompactCard from '../common/CompactCard.tsx';
import TileLabel from '../common/TileLabel.tsx';
import { formatTimestamp } from '../../utils/formatting.ts';
import { fetchForecast } from '../../api/client.ts';
import type { LocalForecast } from '../../api/types.ts';

export default function HeroTemperatureTile() {
  const { currentConditions: cc } = useWeatherData();
  const isMobile = useCompact();

  const value = cc?.temperature?.outside?.value ?? null;
  const unit = cc?.temperature?.outside?.unit ?? 'F';
  const high = cc?.daily_extremes?.outside_temp_hi?.value ?? null;
  const low = cc?.daily_extremes?.outside_temp_lo?.value ?? null;
  const highAt = cc?.daily_extremes?.outside_temp_hi?.at ?? null;
  const lowAt = cc?.daily_extremes?.outside_temp_lo?.at ?? null;

  const [forecast, setForecast] = useState<LocalForecast | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchForecast()
        .then((r) => { if (!cancelled) setForecast(r.local ?? null); })
        .catch(() => { /* hero shows temperature with or without a forecast */ });
    };
    load();
    const id = setInterval(load, 5 * 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (isMobile) {
    return (
      <CompactCard
        label="Outside Air"
        secondary={
          high != null || low != null ? (
            <span>
              H {high != null ? `${high.toFixed(0)}°` : '--'} / L{' '}
              {low != null ? `${low.toFixed(0)}°` : '--'}
            </span>
          ) : undefined
        }
      >
        <span style={{
          fontSize: 'calc(28px * var(--font-scale))',
          fontFamily: 'var(--font-gauge)',
          fontWeight: 'bold',
        }}>
          {value != null ? `${value.toFixed(1)}°${unit}` : '--.-°'}
        </span>
      </CompactCard>
    );
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      padding: '16px',
      background: 'var(--color-bg-card)',
      borderRadius: 'var(--gauge-border-radius, 16px)',
      border: '1px solid var(--color-border)',
      boxShadow: 'var(--gauge-shadow)',
      height: '100%',
      boxSizing: 'border-box',
    }}>
      <TileLabel>Outside Air</TileLabel>

      {/* Numeral + unit — display type role carries the italic serif on paper. */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '4px',
        margin: '2px 0 8px 0',
        lineHeight: 1,
      }}>
        <span style={{
          fontFamily: 'var(--type-display-family)',
          fontSize: 'var(--type-display-size)',
          fontWeight: 'var(--type-display-weight)',
          fontStyle: 'var(--type-display-style)',
          color: 'var(--color-text)',
          lineHeight: 1,
        }}>
          {value != null ? value.toFixed(1) : '—'}
        </span>
        <span style={{
          fontFamily: 'var(--type-display-family)',
          fontSize: 'calc(28px * var(--font-scale))',
          fontWeight: 'var(--type-display-weight)',
          fontStyle: 'var(--type-display-style)',
          color: 'var(--color-text-secondary)',
          marginTop: '6px',
        }}>
          &deg;{unit}
        </span>
      </div>

      {/* Zambretti sentence */}
      {forecast && (
        <>
          <div style={{
            fontFamily: 'var(--type-heading-family)',
            fontSize: 'calc(18px * var(--font-scale))',
            fontWeight: 'var(--type-heading-weight)',
            fontStyle: 'var(--type-heading-style)',
            color: 'var(--color-text)',
            lineHeight: 1.3,
            marginBottom: '4px',
          }}>
            {forecast.text}
          </div>
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'calc(10px * var(--font-scale))',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--color-text-muted)',
          }}>
            Zambretti &middot; {forecast.confidence}% confidence
          </div>
        </>
      )}

      {/* H/L chips at the bottom of the tile */}
      {(high != null || low != null) && (
        <div style={{
          display: 'flex',
          gap: '8px',
          marginTop: 'auto',
          paddingTop: '12px',
          flexWrap: 'wrap',
        }}>
          {high != null && (
            <Chip color="var(--color-temp-hot)">
              High {high.toFixed(1)}&deg;{highAt ? ` · ${formatTimestamp(highAt)}` : ''}
            </Chip>
          )}
          {low != null && (
            <Chip color="var(--color-temp-cold)">
              Low {low.toFixed(1)}&deg;{lowAt ? ` · ${formatTimestamp(lowAt)}` : ''}
            </Chip>
          )}
        </div>
      )}
    </div>
  );
}

function Chip({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span style={{
      display: 'inline-block',
      padding: '4px 10px',
      border: `1px solid ${color}`,
      borderRadius: '4px',
      fontFamily: 'var(--font-gauge)',
      fontSize: 'calc(12px * var(--font-scale))',
      color: color,
      whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

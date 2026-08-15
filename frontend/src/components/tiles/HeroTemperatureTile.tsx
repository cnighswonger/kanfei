/**
 * Typographic outside-air tile.  Big display-role numeral, Zambretti
 * sentence + confidence footer, two H/L chips at the tile bottom.
 * Consumes ``--type-display-*`` CSS variables emitted by ThemeContext;
 * paper themes carry an italic serif display role, non-paper themes a
 * heading sans.
 */
import { useEffect, useState } from 'react';
import { useWeatherData } from '../../context/WeatherDataContext.tsx';
import { useTheme } from '../../context/ThemeContext.tsx';
import { useCompact } from '../../dashboard/CompactContext.tsx';
import CompactCard from '../common/CompactCard.tsx';
import TileLabel from '../common/TileLabel.tsx';
import { formatTimestamp } from '../../utils/formatting.ts';
import { fetchForecast } from '../../api/client.ts';
import type { LocalForecast } from '../../api/types.ts';

export default function HeroTemperatureTile() {
  const { currentConditions: cc } = useWeatherData();
  const { theme } = useTheme();
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
        .catch(() => { /* forecast is optional; hero still renders the temperature */ });
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

  // Read theme.type roles directly rather than via CSS custom
  // properties.  Previous CSS-var path resolved but the italic
  // fontStyle wasn't applying on paper (rendered upright 72 px
  // instead of italic 104 px per REVIEW-04) — going through the
  // theme object bypasses whatever was intercepting the vars.
  const display = theme.type.display;
  const title = theme.type.title;
  const sectionLabel = theme.type.sectionLabel;

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

      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '4px',
        margin: '2px 0 8px 0',
        lineHeight: 1,
      }}>
        <span
          data-role="hero-value"
          style={{
            fontFamily: display.family,
            fontSize: `calc(${display.size}px * var(--font-scale))`,
            fontWeight: display.weight,
            fontStyle: display.italic ? 'italic' : 'normal',
            color: 'var(--color-text)',
            lineHeight: 1,
          }}
        >
          {value != null ? value.toFixed(1) : '—'}
        </span>
        <span style={{
          fontFamily: display.family,
          fontSize: `calc(${Math.round(display.size * 0.35)}px * var(--font-scale))`,
          fontWeight: display.weight,
          fontStyle: display.italic ? 'italic' : 'normal',
          color: 'var(--color-text-secondary)',
          marginTop: '6px',
        }}>
          &deg;{unit}
        </span>
      </div>

      {forecast && (
        <>
          <div style={{
            fontFamily: title.family,
            fontSize: `calc(${title.size}px * var(--font-scale))`,
            fontWeight: title.weight,
            fontStyle: title.italic ? 'italic' : 'normal',
            color: 'var(--color-text)',
            lineHeight: 1.3,
            marginBottom: '4px',
          }}>
            {forecast.text}
          </div>
          <div style={{
            fontFamily: sectionLabel.family,
            fontSize: `calc(${sectionLabel.size}px * var(--font-scale))`,
            fontWeight: sectionLabel.weight,
            letterSpacing: sectionLabel.tracking != null ? `${sectionLabel.tracking}px` : undefined,
            textTransform: sectionLabel.transform ?? 'uppercase',
            color: 'var(--color-text-muted)',
          }}>
            Zambretti &middot; {forecast.confidence}% confidence
          </div>
        </>
      )}

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

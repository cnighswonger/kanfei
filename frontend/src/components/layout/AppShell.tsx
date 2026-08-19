import { useState, useEffect, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';
import Footer from './Footer';
import WeatherBackground from '../WeatherBackground';
import { useWeatherBackground } from '../../context/WeatherBackgroundContext';
import { useTheme } from '../../context/ThemeContext';
import { useWeatherData } from '../../context/WeatherDataContext';
import { useIsMobile } from '../../hooks/useIsMobile';
import { useMuteStatus } from '../../hooks/useMuteStatus';

const CHANNEL_LABELS: Record<string, string> = {
  outdoor_temperature: 'Outdoor Temperature',
  outdoor_humidity: 'Outdoor Humidity',
  wind_speed: 'Wind Speed',
  wind_direction: 'Wind Direction',
  wind_gust: 'Wind Gust',
  barometer: 'Barometer',
  rain_daily: 'Rain (Daily)',
  rain_hour: 'Rain (Hourly)',
  rain_24h: 'Rain (24 Hour)',
  solar_radiation: 'Solar Radiation',
  uv_index: 'UV Index',
};

interface AppShellProps {
  children: ReactNode;
  connected?: boolean;
  lastUpdate?: Date | null;
}

export default function AppShell({
  children,
  connected = false,
  lastUpdate = null,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { enabled } = useWeatherBackground();
  const { theme } = useTheme();
  const themeOwnsBackground = theme.surface.ownsBackground;
  const { nowcastWarning, dismissNowcastWarning } = useWeatherData();
  const isMobile = useIsMobile();
  const channelMuted = useMuteStatus();

  // Auto-dismiss warning after 30 seconds.
  useEffect(() => {
    if (!nowcastWarning) return;
    const timer = setTimeout(dismissNowcastWarning, 30_000);
    return () => clearTimeout(timer);
  }, [nowcastWarning, dismissNowcastWarning]);

  const location = useLocation();
  const isAbout = location.pathname === '/about';
  const hideHeader = isAbout && !isMobile;
  // Desktop sidebar is always the labelled 220 px per Design's SCREENS.md
  // spec.  The earlier collapse-to-icon-rail toggle was removed after
  // Design flagged it in the v32 review — the labelled colour-keyed nav
  // is load-bearing on every page.  Mobile still uses ``sidebarOpen``
  // (overlay pattern) to hide/show.
  const sidebarWidth = '220px';

  // A paper theme owns the page background: body's texture layer
  // and the plate below both need to show through, so the shell
  // renders transparent.  Non-paper themes only go transparent when
  // WeatherBackground is active (unchanged from pre-refactor
  // behaviour).
  const shellTransparent = enabled || themeOwnsBackground;

  return (
    <>
      <WeatherBackground />
      {/* Scrim — sits over the WeatherBackground image and under all
          content.  Renders only when the active theme provides a
          scrim colour AND the user has a weather background enabled.
          Purpose: guarantee a floor contrast so tiles / hairlines /
          labels stay legible against any photograph.  Design's
          DIFF-dark-background.md.  Paper themes ship no scrim and
          own their own background, so this stays hidden there. */}
      {enabled && theme.surface.scrim && (
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'var(--surface-scrim, transparent)',
            pointerEvents: 'none',
            zIndex: 2,
          }}
        />
      )}
      {/* Ornamental plate layer.  Reads --plate-* custom properties
          published by applyThemeToDOM.  Non-paper themes ship
          --plate-image: none, so the element paints nothing — safe
          to leave permanently mounted.  Suppressed on the dashboard
          route: the dashboard renders its own scoped corner plate
          via --surface-plate, and painting both duplicates the
          engraving across the page. */}
      {/* Ornamental plate — dashboard renders its own scoped corner
          plate via ``--surface-plate``, so we suppress the shell-wide
          layer there.  Also suppressed on Settings per Design's v32
          review: Settings is a work surface, the plate sits behind
          form inputs (Location map, Channel Mute grid) and becomes
          the subject of the page.  If a paper texture is wanted the
          theme's ``surface.texture`` gradient already provides one
          at a weight that doesn't compete. */}
      {location.pathname !== '/' && location.pathname !== '/settings' && (
        <div className="app-plate" aria-hidden="true" />
      )}
      <div
        style={{
          display: 'grid',
          gridTemplateRows: hideHeader ? '0px 1fr' : (themeOwnsBackground ? '60px 1fr' : '56px 1fr'),
          gridTemplateColumns: `${sidebarWidth} 1fr`,
          gridTemplateAreas: `
            "header header"
            "sidebar main"
          `,
          height: '100vh',
          background: shellTransparent ? 'transparent' : 'var(--color-bg)',
          position: 'relative',
          zIndex: 3,
          transition: 'background-color 0.3s ease, grid-template-columns 0.2s ease',
        }}
        className="app-shell"
      >
        <div style={{ gridArea: 'header', overflow: 'hidden' }}>
          <Header
            connected={connected}
            onMenuToggle={() => setSidebarOpen((prev) => !prev)}
            sidebarOpen={sidebarOpen}
          />
        </div>

        <div style={{ gridArea: 'sidebar' }}>
          <Sidebar
            open={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />
        </div>

        <main
          style={{
            gridArea: 'main',
            marginTop: isMobile ? '10px' : hideHeader ? (themeOwnsBackground ? '60px' : '56px') : '5px',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          <div
            className="app-main-content"
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            {nowcastWarning && (
              <div
                role="alert"
                onClick={dismissNowcastWarning}
                style={{
                  padding: '10px 16px',
                  margin: '24px 24px 0 24px',
                  background: 'var(--color-warning-bg, #664d03)',
                  color: 'var(--color-warning-text, #fff3cd)',
                  border: '1px solid var(--color-warning-border, #997404)',
                  borderRadius: 8,
                  fontSize: "calc(13px * var(--font-scale))",
                  fontFamily: 'var(--font-body)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span style={{ flexShrink: 0 }}>{'\u26A0'}</span>
                <span style={{ flex: 1 }}>{nowcastWarning}</span>
                <span style={{ flexShrink: 0, opacity: 0.7, fontSize: "calc(11px * var(--font-scale))" }}>click to dismiss</span>
              </div>
            )}
            {channelMuted.length > 0 && (
              <div
                role="status"
                style={{
                  padding: '10px 16px',
                  margin: '24px 24px 0 24px',
                  background: 'var(--color-warning-bg, #664d03)',
                  color: 'var(--color-warning-text, #fff3cd)',
                  border: '1px solid var(--color-warning-border, #997404)',
                  borderRadius: 8,
                  fontSize: "calc(13px * var(--font-scale))",
                  fontFamily: 'var(--font-body)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span style={{ flexShrink: 0 }}>{'⚠'}</span>
                <span style={{ flex: 1 }}>
                  Muted channels —{' '}
                  {channelMuted
                    .map((c) => CHANNEL_LABELS[c] ?? c)
                    .join(', ')}
                  . Other stations and aggregators will receive &lsquo;missing
                  value&rsquo; for these until you re-enable them in Settings
                  &rarr; Channel Mute.
                </span>
              </div>
            )}
            {children}
          </div>
          <Footer lastUpdate={lastUpdate} />
        </main>
      </div>
    </>
  );
}

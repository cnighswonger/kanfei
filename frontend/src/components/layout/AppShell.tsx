import { useState, useEffect, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import Header from './Header';
import Sidebar from './Sidebar';
import Footer from './Footer';
import WeatherBackground from '../WeatherBackground';
import { useWeatherBackground } from '../../context/WeatherBackgroundContext';
import { useWeatherData } from '../../context/WeatherDataContext';
import { useIsMobile } from '../../hooks/useIsMobile';
import { readUIPref, writeUIPref, syncUIPrefs } from '../../utils/uiPrefs';

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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => readUIPref("ui_sidebar_collapsed", "false") === "true",
  );
  const { enabled } = useWeatherBackground();
  const { nowcastWarning, dismissNowcastWarning } = useWeatherData();
  const isMobile = useIsMobile();

  // Auto-dismiss warning after 30 seconds.
  useEffect(() => {
    if (!nowcastWarning) return;
    const timer = setTimeout(dismissNowcastWarning, 30_000);
    return () => clearTimeout(timer);
  }, [nowcastWarning, dismissNowcastWarning]);

  // Reconcile sidebar state with backend on mount
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const v = prefs["ui_sidebar_collapsed"];
      if (v !== undefined) {
        setSidebarCollapsed(v === "true");
      }
    });
  }, []);

  const toggleCollapse = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      writeUIPref("ui_sidebar_collapsed", String(next));
      return next;
    });
  };

  const location = useLocation();
  const isAbout = location.pathname === '/about';
  const hideHeader = isAbout && !isMobile;
  const sidebarWidth = sidebarCollapsed ? '56px' : '220px';

  return (
    <>
      <WeatherBackground />
      <div
        style={{
          display: 'grid',
          gridTemplateRows: hideHeader ? '0px 1fr' : '56px 1fr',
          gridTemplateColumns: `${sidebarWidth} 1fr`,
          gridTemplateAreas: `
            "header header"
            "sidebar main"
          `,
          height: '100vh',
          background: enabled ? 'transparent' : 'var(--color-bg)',
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
            collapsed={sidebarCollapsed}
            onToggleCollapse={toggleCollapse}
          />
        </div>

        <main
          style={{
            gridArea: 'main',
            marginTop: isMobile ? '10px' : hideHeader ? '56px' : '5px',
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
                  fontSize: 13,
                  fontFamily: 'var(--font-body)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <span style={{ flexShrink: 0 }}>{'\u26A0'}</span>
                <span style={{ flex: 1 }}>{nowcastWarning}</span>
                <span style={{ flexShrink: 0, opacity: 0.7, fontSize: 11 }}>click to dismiss</span>
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

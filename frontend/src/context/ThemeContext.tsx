import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { themes, defaultTheme, type Theme } from '../themes';
import { readUIPref, writeUIPref, syncUIPrefs } from '../utils/uiPrefs';

interface ThemeContextValue {
  theme: Theme;
  themeName: string;
  setThemeName: (name: string) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const PREF_KEY = 'ui_theme';

// Color keys managed by WeatherBackground when active — skip to avoid
// overwriting the rgba overrides that make tiles transparent.
const WEATHER_BG_KEYS = new Set([
  'bgCard', 'bgCardHover', 'bgSecondary', 'headerBg', 'sidebarBg',
]);

function applyThemeToDOM(theme: Theme) {
  const root = document.documentElement;
  const skipWeatherBg = root.dataset.weatherBg === 'active';

  // Apply color CSS custom properties
  for (const [key, value] of Object.entries(theme.colors)) {
    if (skipWeatherBg && WEATHER_BG_KEYS.has(key)) continue;
    const cssVar = `--color-${key.replace(/([A-Z])/g, '-$1').toLowerCase()}`;
    root.style.setProperty(cssVar, value);
  }

  // Apply font CSS custom properties
  root.style.setProperty('--font-body', theme.fonts.body);
  root.style.setProperty('--font-heading', theme.fonts.heading);
  root.style.setProperty('--font-mono', theme.fonts.mono);
  root.style.setProperty('--font-gauge', theme.fonts.gauge);

  // Apply gauge CSS custom properties
  root.style.setProperty('--gauge-stroke-width', String(theme.gauge.strokeWidth));
  root.style.setProperty('--gauge-bg-opacity', String(theme.gauge.bgOpacity));
  root.style.setProperty('--gauge-shadow', theme.gauge.shadow);
  root.style.setProperty('--gauge-border-radius', theme.gauge.borderRadius);
}

function getInitialThemeName(): string {
  const stored = readUIPref(PREF_KEY, defaultTheme);
  return (stored in themes) ? stored : defaultTheme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeName, setThemeNameState] = useState<string>(getInitialThemeName);

  const theme = themes[themeName] ?? themes[defaultTheme];

  const setThemeName = useCallback((name: string) => {
    if (name in themes) {
      setThemeNameState(name);
      writeUIPref(PREF_KEY, name);
    }
  }, []);

  useEffect(() => {
    applyThemeToDOM(theme);
  }, [theme]);

  // Reconcile with backend on mount
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const synced = prefs[PREF_KEY];
      if (synced && synced in themes && synced !== themeName) {
        setThemeNameState(synced);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, themeName, setThemeName }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return ctx;
}

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import Highcharts from 'highcharts';
import { themes, defaultTheme, type Theme } from '../themes';
import { readUIPref, writeUIPref, syncUIPrefs } from '../utils/uiPrefs';
import { highchartsTheme } from '../utils/highchartsTheme';

interface ThemeContextValue {
  theme: Theme;
  themeName: string;
  setThemeName: (name: string) => void;
  /** The persisted custom theme (null if none saved). */
  customTheme: Theme | null;
  /** Persist a custom theme and switch to it. */
  setCustomTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

const PREF_KEY = 'ui_theme';
const CUSTOM_THEME_KEY = 'ui_custom_theme';

// Color keys managed by WeatherBackground when active — skip to avoid
// overwriting the rgba overrides that make tiles transparent.
const WEATHER_BG_KEYS = new Set([
  'bgCard', 'bgCardHover', 'bgSecondary', 'headerBg', 'sidebarBg',
]);

/** Apply a theme's CSS custom properties to the document root.
 *  Exported so the theme editor can call it for live preview.
 *
 *  UI refactor PR 2 (ui/refactor): extended to publish the new token
 *  groups introduced with the paper themes.  Existing consumers keep
 *  reading the old variables unchanged; new consumers land alongside
 *  their screens in later PRs.
 */
export function applyThemeToDOM(theme: Theme) {
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
  root.style.setProperty('--font-display', theme.fonts.display);

  // Type roles.  One triplet per role (family / size / weight) plus
  // tracking + transform + style when set.  Consumers pull like
  // ``font-family: var(--type-heading-family)``.
  //
  // Role names keep their camelCase form (``sectionLabel`` publishes
  // as ``--type-sectionLabel-*``, not kebab-case) so Design's
  // ``primitives.tsx`` ``type(role)`` helper — which templates the
  // role name straight into the var — resolves.  The earlier
  // kebab-case emission was the "fonts are off" root cause: every
  // ``var(--type-sectionLabel-family)`` lookup missed the published
  // ``--type-section-label-family`` and silently inherited body sans.
  for (const [roleName, r] of Object.entries(theme.type)) {
    const p = `--type-${roleName}`;
    root.style.setProperty(`${p}-family`, r.family);
    root.style.setProperty(`${p}-size`, `calc(${r.size}px * var(--font-scale))`);
    root.style.setProperty(`${p}-weight`, String(r.weight));
    root.style.setProperty(`${p}-tracking`, r.tracking != null ? `${r.tracking}px` : 'normal');
    root.style.setProperty(`${p}-transform`, r.transform ?? 'none');
    root.style.setProperty(`${p}-style`, r.italic ? 'italic' : 'normal');
  }

  // Rules — row separators.
  root.style.setProperty('--rule-width', `${theme.rules.hairline}px`);
  root.style.setProperty('--rule-style', theme.rules.style);
  root.style.setProperty('--rule-strong', theme.rules.strong);
  root.style.setProperty('--rule-hair', theme.rules.hair);

  // Radius.
  root.style.setProperty('--radius-card', theme.radius.card);
  root.style.setProperty('--radius-control', theme.radius.control);

  // Surface texture — a subtle radial-gradient warmth layer wired
  // into `body { background-image: ... }` in index.css.  Non-paper
  // themes ship 'none', so the CSS rule is invisible there.
  root.style.setProperty('--surface-texture', theme.surface.texture ?? 'none');

  // Surface plate — the ornamental engraving that gives paper themes
  // their identity.  Rendered as a fixed-position layer inside
  // AppShell via a companion `app-plate` element that reads these
  // custom properties.  Non-paper themes ship `--plate-image: none`,
  // which makes the layer invisible even though the element still
  // renders.  `--plate-owns-background` is a numeric 0/1 flag other
  // shell CSS uses to know whether to leave the app-shell background
  // transparent so this plate shows through.
  const plate = theme.surface.plate;
  root.style.setProperty('--plate-image', plate ? `url("${plate.src}")` : 'none');
  root.style.setProperty('--plate-opacity', plate ? String(plate.opacity) : '0');
  root.style.setProperty('--plate-filter', plate?.filter ?? 'none');
  root.style.setProperty('--plate-blend', plate?.blend ?? 'normal');
  root.style.setProperty('--plate-position', plate?.position ?? 'center');
  root.style.setProperty('--plate-size', plate?.size ?? 'contain');
  // Alias for Design's newer dashboard components that read the plate
  // via `--surface-plate` (v12 EverydayDashboard).  Same URL as the
  // shell's `--plate-image`; different scope (dashboard-corner vs
  // shell-wide).  ``none`` when no plate is configured.
  root.style.setProperty('--surface-plate', plate ? `url("${plate.src}")` : 'none');
  root.style.setProperty('--surface-owns-background', theme.surface.ownsBackground ? '1' : '0');
  // Scrim + tile glass — Dark ships values here (Design's
  // DIFF-dark-background.md).  Paper themes leave them unset so the
  // consuming CSS falls back to transparent / none.
  root.style.setProperty('--surface-scrim', theme.surface.scrim ?? 'transparent');
  root.style.setProperty('--tile-bg', theme.surface.tileBg ?? 'transparent');
  root.style.setProperty('--tile-backdrop', theme.surface.tileBackdrop ?? 'none');

  // Chart tokens.  Series colours as one var each so Highcharts
  // callers can pick them by role rather than by index.
  const chart = theme.chart;
  root.style.setProperty('--chart-grid', chart.grid);
  root.style.setProperty('--chart-grid-soft', chart.gridSoft);
  root.style.setProperty('--chart-grid-minor', chart.gridMinor);
  root.style.setProperty('--chart-grid-major', chart.gridMajor);
  root.style.setProperty('--chart-axis', chart.axis);
  root.style.setProperty('--chart-trace', chart.trace);
  root.style.setProperty('--chart-trace-shadow', chart.traceShadow ?? 'transparent');
  root.style.setProperty('--chart-trace-fill-opacity', String(chart.traceFillOpacity));
  root.style.setProperty('--chart-trace-secondary', chart.traceSecondary);
  root.style.setProperty('--chart-surface', chart.surface);
  for (const [seriesName, hex] of Object.entries(chart.series)) {
    root.style.setProperty(`--chart-series-${seriesName}`, hex);
  }

  // Dial band radii (fractions of the wheel-barometer radius).
  for (const [band, fraction] of Object.entries(theme.dial)) {
    root.style.setProperty(`--dial-${band.replace(/([A-Z])/g, '-$1').toLowerCase()}`, String(fraction));
  }

  // Apply gauge CSS custom properties
  root.style.setProperty('--gauge-stroke-width', String(theme.gauge.strokeWidth));
  root.style.setProperty('--gauge-bg-opacity', String(theme.gauge.bgOpacity));
  root.style.setProperty('--gauge-shadow', theme.gauge.shadow);
  root.style.setProperty('--gauge-border-radius', theme.gauge.borderRadius);

  // Apply global font-size multiplier. Consumers read this via
  // `calc(Npx * var(--font-scale))` in inline styles.
  root.style.setProperty('--font-scale', String(theme.fontScale ?? 1));
}

function deserializeCustomTheme(raw: string): Theme | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    // Basic validation: must have colors, fonts, gauge objects
    if (parsed?.colors && parsed?.fonts && parsed?.gauge) {
      // Backfill any group missing from a pre-refactor custom theme —
      // ``type``, ``rules``, ``radius``, ``surface``, ``chart``,
      // ``dial``, ``colors.sky``, ``colors.surfaceSunken``,
      // ``fonts.display`` were introduced with the UI refactor.
      // Consumers that only touch existing fields keep working; new
      // consumers get sensible defaults from the current base theme
      // rather than ``undefined`` at runtime.
      const base = themes[defaultTheme];
      const fontScale = typeof parsed.fontScale === 'number' ? parsed.fontScale : 1;
      return {
        ...base,
        ...parsed,
        name: 'custom',
        label: 'Custom',
        fontScale,
        colors: { ...base.colors, ...parsed.colors },
        fonts: { ...base.fonts, ...parsed.fonts },
        type: { ...base.type, ...parsed.type },
        rules: { ...base.rules, ...parsed.rules },
        radius: { ...base.radius, ...parsed.radius },
        surface: { ...base.surface, ...parsed.surface },
        chart: {
          ...base.chart,
          ...parsed.chart,
          series: { ...base.chart.series, ...(parsed.chart?.series ?? {}) },
        },
        dial: { ...base.dial, ...parsed.dial },
        gauge: { ...base.gauge, ...parsed.gauge },
      };
    }
  } catch { /* corrupt JSON */ }
  return null;
}

function getInitialThemeName(): string {
  const stored = readUIPref(PREF_KEY, defaultTheme);
  if (stored === 'custom') return 'custom';
  return (stored in themes) ? stored : defaultTheme;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeName, setThemeNameState] = useState<string>(getInitialThemeName);
  const [customTheme, setCustomThemeState] = useState<Theme | null>(() =>
    deserializeCustomTheme(readUIPref(CUSTOM_THEME_KEY, '')),
  );

  const theme = themeName === 'custom' && customTheme
    ? customTheme
    : themes[themeName] ?? themes[defaultTheme];

  const setThemeName = useCallback((name: string) => {
    if (name === 'custom' || name in themes) {
      setThemeNameState(name);
      writeUIPref(PREF_KEY, name);
    }
  }, []);

  const setCustomTheme = useCallback((t: Theme) => {
    const tagged = { ...t, name: 'custom', label: 'Custom' };
    setCustomThemeState(tagged);
    writeUIPref(CUSTOM_THEME_KEY, JSON.stringify(tagged));
    setThemeNameState('custom');
    writeUIPref(PREF_KEY, 'custom');
  }, []);

  useEffect(() => {
    applyThemeToDOM(theme);
    // Highcharts token bridge (Design v34 HIGHCHARTS.md, tranche 1).
    // Order matters: applyThemeToDOM writes the CSS vars to :root
    // synchronously, and highchartsTheme() reads them via
    // getComputedStyle on the same event-loop turn.  setOptions
    // updates the default options object every subsequent chart
    // inherits — already-mounted charts do NOT auto-repaint, so a
    // theme swap while a chart is on screen keeps the old skin until
    // the chart re-renders (data change, resize, remount).  That's
    // acceptable given the flat-tokens-only surface here; the
    // existing consumers memoise their options on theme name.
    Highcharts.setOptions(highchartsTheme());
  }, [theme]);

  // Reconcile with backend on mount
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const synced = prefs[PREF_KEY];
      if (synced && synced !== themeName) {
        if (synced === 'custom' || synced in themes) {
          setThemeNameState(synced);
        }
      }
      const syncedCustom = prefs[CUSTOM_THEME_KEY];
      if (syncedCustom) {
        const parsed = deserializeCustomTheme(syncedCustom);
        if (parsed) setCustomThemeState(parsed);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, themeName, setThemeName, customTheme, setCustomTheme }}>
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

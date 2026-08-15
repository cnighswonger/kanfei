/**
 * Extended Theme contract.
 *
 * Additive to the shipping interface: every field the previous
 * ``dark.ts`` / ``light.ts`` / ``classic.ts`` set keeps its name and
 * meaning, so ``ThemeContext.applyThemeToDOM()`` and
 * ``ThemeEditor.tsx`` keep working while the new groups get wired.
 * The new groups exist because the paper themes need axes the
 * previous colour table couldn't express:
 *
 *   - ``type``      per-role face + size + weight + tracking + italic.
 *                   Glaisher's section labels are tracked mono small
 *                   caps and its display face is an italic serif;
 *                   ``fonts`` alone couldn't say that.
 *   - ``rules``     hairline vs dotted row separators
 *                   (Tokens.kt ``KanfeiRules`` in the Android app).
 *   - ``radius``    dark/light are 16px rounded, classic 8px,
 *                   paper themes square.
 *   - ``surface``   paper-texture gradient + optional engraving plate,
 *                   so screens stop hardcoding them.  Also carries
 *                   ``ownsBackground`` — when true, the theme replaces
 *                   the weather-background layer instead of
 *                   compositing with it (paper themes).
 *   - ``chart``     ledger + Highcharts colours in one place.  Every
 *                   chart series gets its OWN hex; never reuse the
 *                   four semantic accents or two series collide.
 *   - ``dial``      wheel-barometer band radii as fractions of the
 *                   dial radius, so the graduation / numeral / zone /
 *                   needle order is data rather than per-theme
 *                   drawing code.
 *
 * ⚠ Two rules that caused real bugs in the mocks — worth reading
 * before writing chart or gauge code:
 *
 * - **``chart.series.*`` is plot ink only.**  Those hexes are tuned
 *   as 2px strokes against ``chart.grid``; several land at 3.3-4.4:1
 *   and fail AA as label text.  A coloured value in a table row uses
 *   ``text`` / ``textSecondary`` with weight or a swatch carrying
 *   the meaning.  Same for the semantic accents (success / warning /
 *   danger) below small type.
 *
 * - **Derive graphics from the same numbers the labels print.**
 *   Every defect the Astronomy design review caught was a marker,
 *   arc, or band computed independently of the value beside it.
 *   Sample the series that drew the curve; map times through one
 *   shared axis function.
 */

import dark from './dark';
import light from './light';
import classic from './classic';
import glaisher from './glaisher';
import mammoth from './mammoth';

export interface TypeRole {
  family: string;
  size: number;
  weight: number;
  italic?: boolean;
  /** letter-spacing in px. */
  tracking?: number;
  transform?: 'none' | 'uppercase';
}

export interface Theme {
  name: string;
  label: string;
  colors: {
    bg: string;
    bgSecondary: string;
    bgCard: string;
    bgCardHover: string;
    text: string;
    textSecondary: string;
    textMuted: string;
    accent: string;
    accentHover: string;
    accentMuted: string;
    success: string;
    warning: string;
    danger: string;
    border: string;
    borderLight: string;
    gaugeTrack: string;
    gaugeFill: string;
    tempHot: string;
    tempCold: string;
    tempMid: string;
    barometerNeedle: string;
    windArrow: string;
    rainBlue: string;
    humidityGreen: string;
    solarYellow: string;
    headerBg: string;
    sidebarBg: string;
    /** Cool atmospheric ink — ledger rules, dew-point trace, precip bars. */
    sky: string;
    /** Recessed surface behind charts and ledgers (``paperDeep`` on the paper themes). */
    surfaceSunken: string;
  };
  fonts: {
    body: string;
    heading: string;
    mono: string;
    gauge: string;
    /** Masthead / hero numerals. Italic serif on the paper themes. */
    display: string;
  };
  type: {
    display: TypeRole;
    heading: TypeRole;
    title: TypeRole;
    body: TypeRole;
    mono: TypeRole;
    /** Tracked small caps above each block. */
    sectionLabel: TypeRole;
  };
  rules: {
    /** Separator width in px. */
    hairline: number;
    /** Row separators: solid hairlines (Glaisher) or dotted (Mammoth). */
    style: 'solid' | 'dotted';
    /** Rule colour at full strength, e.g. under a section heading. */
    strong: string;
    /** Rule colour for repeated row separators. */
    hair: string;
  };
  radius: {
    /** Cards, tiles, panels. '0' on the paper themes. */
    card: string;
    /** Buttons, selects, inputs. */
    control: string;
  };
  surface: {
    /** Optional background-image applied to the app shell (paper texture). */
    texture?: string;
    /**
     * True when the theme owns the page background outright: the
     * paper ground plus its engraving plates REPLACE the weather-
     * background layer instead of compositing with it.  While active,
     * ``WeatherBackground`` must not render, and the
     * background-visibility / card-transparency controls in the
     * Display tab should be disabled with a short note explaining
     * why — a condition gradient or a user-uploaded scene photo
     * behind cream paper and multiply-blended engravings reads as
     * mud.  Precedent: ``pages/About.tsx`` already replaces the
     * weather background for one view with its own full-page plate.
     *
     * Wired in the shell/settings PR (PR 4), not this one.
     */
    ownsBackground: boolean;
    /** Engraving plate for the shell, when ``ownsBackground`` is true. */
    plate?: {
      src: string;
      opacity: number;
      /** CSS filter, e.g. ``sepia(0.55) contrast(1.05) saturate(0.9)``. */
      filter: string;
      blend: 'multiply' | 'normal';
      position: string;
      size: 'cover' | 'contain';
    };
  };
  /**
   * Chart colour tables, ledger + Highcharts in one place.
   *
   * ``series.*`` is the multi-series ramp — each series gets its own
   * hex so two adjacent lines (temperature vs pressure, dew vs
   * rain) never collide.  Feed straight to Highcharts
   * ``series[].color``.
   *
   * PLOT INK ONLY.  These hexes are tuned as 2px strokes / fills
   * against ``grid``; several land near 3.3-4.4:1 on their own
   * surface and fail AA at label sizes.  For a coloured value in a
   * table or card row, use ``text`` / ``textSecondary`` and carry the
   * meaning with weight, a swatch, or an icon beside it.
   *
   * ``trace`` / ``traceSecondary`` / ``traceShadow`` / ``traceFillOpacity``
   * are the single-primary-trace slot the History areaspline uses;
   * ``surface`` is the chart plot background; ``gridMinor`` /
   * ``gridMajor`` are the Highcharts axis-grid names History
   * currently reads via ``getComputedStyle``.
   */
  chart: {
    series: {
      temp: string;
      dew: string;
      baro: string;
      humidity: string;
      wind: string;
      rain: string;
      solar: string;
      et: string;
    };
    grid: string;
    gridSoft: string;
    axis: string;
    trace: string;
    traceShadow: string | null;
    traceFillOpacity: number;
    traceSecondary: string;
    gridMinor: string;
    gridMajor: string;
    /** Plot background. */
    surface: string;
  };
  /**
   * Wheel-barometer band radii as fractions of the dial radius,
   * outermost first.  Order must hold: graduations outside numerals,
   * numerals outside zone words, needle short of the numeral ring.
   */
  dial: {
    gradOuter: number;
    gradInner: number;
    numeral: number;
    zone: number;
    needle: number;
    trendHand: number;
  };
  gauge: {
    strokeWidth: number;
    bgOpacity: number;
    shadow: string;
    borderRadius: string;
  };
  /** Global font-size multiplier via ``--font-scale``.  Editor clamps 0.85-1.75. */
  fontScale: number;
}

export const themes: Record<string, Theme> = { dark, light, classic, glaisher, mammoth };
/**
 * The shipping default is now ``mammoth`` — "The Mammoth's Log," a paper
 * theme that owns the page background and gives the app a distinct
 * first-view identity instead of the generic dark shell.  Users who
 * saved a different theme (via ThemeContext's localStorage/backend
 * pref) still see their choice; this only changes what a fresh visitor
 * sees.  Keep in sync with backend ``ui_theme`` default in
 * ``backend/app/api/config.py``.
 */
export const defaultTheme = 'mammoth';
export { dark, light, classic, glaisher, mammoth };

/** Deep-merge overrides onto a base preset to create a custom theme.
 *
 * Groups whose fields the ThemeEditor may edit piecemeal deep-merge:
 * a caller passing ``{ chart: { series: { temp: '#…' } } }`` gets a
 * single-series override, not a chart with only one series and every
 * other field blown away.  Same pattern as ``deserializeCustomTheme``
 * uses for legacy custom themes loaded from localStorage.
 */
export function createCustomTheme(
  base: Theme,
  overrides: Partial<{
    colors: Partial<Theme['colors']>;
    fonts: Partial<Theme['fonts']>;
    type: Partial<Theme['type']>;
    rules: Partial<Theme['rules']>;
    radius: Partial<Theme['radius']>;
    surface: Partial<Theme['surface']>;
    chart: Partial<Theme['chart']> & { series?: Partial<Theme['chart']['series']> };
    dial: Partial<Theme['dial']>;
    gauge: Partial<Theme['gauge']>;
    fontScale: number;
  }>,
): Theme {
  return {
    name: 'custom',
    label: 'Custom',
    colors: { ...base.colors, ...overrides.colors },
    fonts: { ...base.fonts, ...overrides.fonts },
    type: { ...base.type, ...overrides.type },
    rules: { ...base.rules, ...overrides.rules },
    radius: { ...base.radius, ...overrides.radius },
    surface: { ...base.surface, ...overrides.surface },
    chart: {
      ...base.chart,
      ...overrides.chart,
      series: { ...base.chart.series, ...(overrides.chart?.series ?? {}) },
    },
    dial: { ...base.dial, ...overrides.dial },
    gauge: { ...base.gauge, ...overrides.gauge },
    fontScale: overrides.fontScale ?? base.fontScale,
  };
}

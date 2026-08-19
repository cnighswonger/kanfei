import type { Theme, TypeRole } from './index';

const role = (
  family: string,
  size: number,
  weight: number,
  extra: Partial<TypeRole> = {},
): TypeRole => ({ family, size, weight, ...extra });

const body = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const heading = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const mono = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace";
const gaugeFont = "'JetBrains Mono', 'Fira Code', monospace";

/**
 * Dark — the shipping default.  Colour, font and gauge values are
 * unchanged from the pre-refactor ``dark.ts``; only the new token
 * groups (type, rules, radius, surface, chart, dial + colors.sky
 * and colors.surfaceSunken + fonts.display) are added.
 */
const dark: Theme = {
  name: 'dark',
  label: 'Dark',
  colors: {
    bg: '#0f1117',
    bgSecondary: '#1a1d28',
    bgCard: '#1e2130',
    bgCardHover: '#252840',
    text: '#e8e9ed',
    textSecondary: '#9ca3b4',
    textMuted: '#5c6478',
    accent: '#3b82f6',
    accentHover: '#2563eb',
    accentMuted: 'rgba(59,130,246,0.15)',
    success: '#22c55e',
    warning: '#f59e0b',
    danger: '#ef4444',
    border: '#2a2d3e',
    borderLight: '#353849',
    gaugeTrack: '#252840',
    gaugeFill: '#3b82f6',
    tempHot: '#ef4444',
    tempCold: '#3b82f6',
    tempMid: '#22c55e',
    barometerNeedle: '#f59e0b',
    windArrow: '#3b82f6',
    rainBlue: '#06b6d4',
    humidityGreen: '#22c55e',
    solarYellow: '#f59e0b',
    headerBg: '#141622',
    sidebarBg: '#141622',
    sky: '#6e8aa8',
    surfaceSunken: '#1a1d28',
  },
  fonts: { body, heading, mono, gauge: gaugeFont, display: heading },
  type: {
    display: role(heading, 64, 700),
    heading: role(heading, 24, 600),
    title: role(heading, 18, 600),
    body: role(body, 14, 400),
    mono: role(mono, 13, 400),
    sectionLabel: role(body, 11, 600, { tracking: 1.4, transform: 'uppercase' }),
  },
  // Hairline raised to rgba(255,255,255,0.14) (was #353849 ≈ 0.08 on
  // the shell surface) so tile borders stay visible over the scrim +
  // user background.  Design's DIFF-dark-background.md — the old
  // hair value was calibrated for a flat ground and disappeared once
  // a photograph sat behind it.
  rules: { hairline: 1, style: 'solid', strong: '#2a2d3e', hair: 'rgba(255,255,255,0.14)' },
  radius: { card: '16px', control: '6px' },
  surface: {
    ownsBackground: false,
    // Sits over the user's weather-background image, under all
    // content.  Guarantees floor contrast against any photograph;
    // without it, legibility depends on the user picking a flat
    // low-contrast wallpaper.  Design's DIFF-dark-background.md.
    scrim: 'rgba(16,19,28,0.74)',
    // Tiles read as glass panels: the photograph still shows between
    // tiles (which is the whole point of allowing one) but the tile
    // itself has a dark ground so numerals don't fight high-frequency
    // detail underneath.
    tileBg: 'rgba(23,27,40,0.82)',
    tileBackdrop: 'blur(3px)',
  },
  chart: {
    series: {
      temp: '#4c8dff',
      dew: '#4fc3f7',
      baro: '#f5c451',
      humidity: '#3ddc84',
      wind: '#ff7a6b',
      rain: '#2e86c8',
      solar: '#f5a341',
      et: '#8b95ab',
    },
    grid: '#232838',
    gridSoft: '#1c2130',
    axis: '#8b95ab',
    trace: '#3b82f6',
    traceShadow: null,
    traceFillOpacity: 0.15,
    traceSecondary: '#06b6d4',
    gridMinor: 'rgba(232,233,237,0.10)',
    gridMajor: 'rgba(232,233,237,0.20)',
    surface: '#1e2130',
  },
  dial: { gradOuter: 0.967, gradInner: 0.887, numeral: 0.747, zone: 0.573, needle: 0.66, trendHand: 0.46 },
  gauge: { strokeWidth: 8, bgOpacity: 0.3, shadow: '0 4px 24px rgba(0,0,0,0.4)', borderRadius: '16px' },
  nav: {
    iconHues: {
      '/': '#4c8dff', '/history': '#b28dff', '/forecast': '#4fc3f7',
      '/astronomy': '#f5c451', '/map': '#3ddc84', '/nowcast': '#ff7a6b',
      '/spray': '#5ec9a7',
    },
  },
  fontScale: 1.0,
};

export default dark;

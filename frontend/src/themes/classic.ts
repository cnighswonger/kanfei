import type { Theme, TypeRole } from './index';

const role = (
  family: string,
  size: number,
  weight: number,
  extra: Partial<TypeRole> = {},
): TypeRole => ({ family, size, weight, ...extra });

const body = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const heading = "Georgia, 'Times New Roman', serif";
const mono = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace";
const gaugeFont = "'Georgia', serif";

/**
 * Classic Instrumental — brass and cream analog aesthetic.  Colour,
 * font and gauge values unchanged from the pre-refactor ``classic.ts``;
 * only the new token groups added.
 */
const classic: Theme = {
  name: 'classic',
  label: 'Classic Instrumental',
  colors: {
    bg: '#f4efe4',
    bgSecondary: '#e8e0d0',
    bgCard: '#faf6ee',
    bgCardHover: '#f0ead8',
    text: '#3a2e1e',
    textSecondary: '#6b5d4a',
    textMuted: '#9a8b74',
    accent: '#8b6914',
    accentHover: '#73570f',
    accentMuted: 'rgba(139,105,20,0.12)',
    success: '#4a7c3f',
    warning: '#b8860b',
    danger: '#a0342e',
    border: '#c9b88c',
    borderLight: '#d9cdaa',
    gaugeTrack: '#e0d5be',
    gaugeFill: '#8b6914',
    tempHot: '#a0342e',
    tempCold: '#3a6b8c',
    tempMid: '#4a7c3f',
    barometerNeedle: '#8b6914',
    windArrow: '#3a6b8c',
    rainBlue: '#3a6b8c',
    humidityGreen: '#4a7c3f',
    solarYellow: '#b8860b',
    headerBg: '#ede6d6',
    sidebarBg: '#ede6d6',
    sky: '#3a6b8c',
    surfaceSunken: '#e8e0d0',
  },
  fonts: { body, heading, mono, gauge: gaugeFont, display: heading },
  type: {
    display: role(heading, 72, 700),
    heading: role(heading, 24, 600),
    title: role(heading, 18, 600),
    body: role(body, 14, 400),
    mono: role(mono, 13, 400),
    sectionLabel: role(body, 11, 600, { tracking: 1.4, transform: 'uppercase' }),
  },
  rules: { hairline: 1, style: 'solid', strong: '#c9b88c', hair: '#d9cdaa' },
  radius: { card: '8px', control: '6px' },
  surface: { ownsBackground: false },
  chart: {
    series: {
      temp: '#8b6914',
      dew: '#3a6b8c',
      baro: '#3a2e1e',
      humidity: '#3f6b35',
      wind: '#a0342e',
      rain: '#5c7f9a',
      solar: '#b8860b',
      et: '#6b5d4a',
    },
    grid: '#c9b88c',
    gridSoft: '#e8e0d0',
    axis: '#6b5d4a',
    trace: '#8b6914',
    traceShadow: null,
    traceFillOpacity: 0.15,
    traceSecondary: '#3a6b8c',
    gridMinor: 'rgba(58,46,30,0.14)',
    gridMajor: 'rgba(58,46,30,0.28)',
    surface: '#faf6ee',
  },
  dial: { gradOuter: 0.967, gradInner: 0.887, numeral: 0.747, zone: 0.573, needle: 0.66, trendHand: 0.46 },
  gauge: { strokeWidth: 6, bgOpacity: 0.2, shadow: '0 2px 16px rgba(58,46,30,0.15)', borderRadius: '8px' },
  nav: {
    iconHues: {
      '/': '#8b6914', '/history': '#6b4a7a', '/forecast': '#3a6b8c',
      '/astronomy': '#7a5c14', '/map': '#3f6b35', '/nowcast': '#5c7f9a',
      '/spray': '#4a6b34',
    },
  },
  fontScale: 1.0,
};

export default classic;

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
 * Light — daytime desk use.  Colour, font and gauge values unchanged
 * from the pre-refactor ``light.ts``; only the new token groups added.
 */
const light: Theme = {
  name: 'light',
  label: 'Light',
  colors: {
    bg: '#f5f6fa',
    bgSecondary: '#ebedf3',
    bgCard: '#ffffff',
    bgCardHover: '#f0f2f8',
    text: '#1a1d28',
    textSecondary: '#5c6478',
    textMuted: '#9ca3b4',
    accent: '#16a34a',
    accentHover: '#15803d',
    accentMuted: 'rgba(22,163,74,0.12)',
    success: '#16a34a',
    warning: '#d97706',
    danger: '#dc2626',
    border: '#d4d8e3',
    borderLight: '#e2e5ef',
    gaugeTrack: '#e2e5ef',
    gaugeFill: '#16a34a',
    tempHot: '#dc2626',
    tempCold: '#2563eb',
    tempMid: '#16a34a',
    barometerNeedle: '#d97706',
    windArrow: '#2563eb',
    rainBlue: '#0891b2',
    humidityGreen: '#16a34a',
    solarYellow: '#d97706',
    headerBg: '#ffffff',
    sidebarBg: '#f0f1f5',
    sky: '#6e8aa8',
    surfaceSunken: '#ebedf3',
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
  rules: { hairline: 1, style: 'solid', strong: '#d4d8e3', hair: '#e2e5ef' },
  radius: { card: '16px', control: '6px' },
  surface: { ownsBackground: false },
  chart: {
    series: {
      temp: '#2563c9',
      dew: '#0f8ab8',
      baro: '#8a6a1f',
      humidity: '#2e7d4f',
      wind: '#b4432f',
      rain: '#1c6ea8',
      solar: '#a8631a',
      et: '#5c6675',
    },
    grid: '#d8dee8',
    gridSoft: '#eef1f6',
    axis: '#5c6675',
    trace: '#16a34a',
    traceShadow: null,
    traceFillOpacity: 0.15,
    traceSecondary: '#0891b2',
    gridMinor: 'rgba(92,100,120,0.14)',
    gridMajor: 'rgba(92,100,120,0.28)',
    surface: '#ffffff',
  },
  dial: { gradOuter: 0.967, gradInner: 0.887, numeral: 0.747, zone: 0.573, needle: 0.66, trendHand: 0.46 },
  gauge: { strokeWidth: 8, bgOpacity: 0.15, shadow: '0 2px 12px rgba(0,0,0,0.08)', borderRadius: '16px' },
  fontScale: 1.0,
};

export default light;

import type { Theme, TypeRole } from './index';

const role = (
  family: string,
  size: number,
  weight: number,
  extra: Partial<TypeRole> = {},
): TypeRole => ({ family, size, weight, ...extra });

const serif = "'Source Serif 4', 'Source Serif Pro', Georgia, serif";
const body = "'Inter', -apple-system, 'Segoe UI', sans-serif";
const mono = "'JetBrains Mono', 'Fira Code', ui-monospace, monospace";

/**
 * The Mammoth's Log — paper theme.  Values from the Android app's
 * ``Tokens.kt`` mammothColors / mammothType (copper accent, dotted
 * rules, Source Serif semibold italic headings, Inter body,
 * JetBrains mono).
 *
 * ``surface.ownsBackground`` is true; the shell/settings PR (PR 4)
 * wires the paper ground and engraving plate to replace the weather
 * background layer.  For now the fields are just declared.
 *
 * Slated to become the ships-with default at the end of the refactor
 * (task 73), replacing dark.
 */
const mammoth: Theme = {
  name: 'mammoth',
  label: "The Mammoth's Log",
  colors: {
    bg: '#ebdfc1',
    bgSecondary: '#dccfa9',
    bgCard: '#ebdfc1',
    bgCardHover: '#e5d8b8',
    text: '#3a2d1d',
    textSecondary: 'rgba(58,45,29,0.84)',
    textMuted: 'rgba(58,45,29,0.75)',
    accent: '#a85f24',
    accentHover: '#8e4f1e',
    accentMuted: 'rgba(168,95,36,0.10)',
    success: '#4e5a2b',
    warning: '#a85f24',
    danger: '#963a2a',
    border: 'rgba(58,45,29,0.24)',
    borderLight: 'rgba(58,45,29,0.24)',
    gaugeTrack: '#dccfa9',
    gaugeFill: '#a85f24',
    tempHot: '#963a2a',
    tempCold: '#3f5d7a',
    tempMid: '#4e5a2b',
    barometerNeedle: '#a85f24',
    windArrow: '#a85f24',
    rainBlue: '#3f5d7a',
    humidityGreen: '#5d6b34',
    solarYellow: '#a85f24',
    headerBg: '#ebdfc1',
    sidebarBg: '#ebdfc1',
    sky: '#6e8aa8',
    surfaceSunken: '#dccfa9',
  },
  fonts: { body, heading: serif, mono, gauge: mono, display: serif },
  type: {
    display: role(serif, 104, 600, { italic: true }),
    heading: role(serif, 29, 600, { italic: true }),
    title: role(serif, 17, 600, { italic: true }),
    body: role(body, 14, 400),
    mono: role(mono, 13, 400),
    sectionLabel: role(mono, 10, 500, { tracking: 2, transform: 'uppercase' }),
  },
  rules: { hairline: 1, style: 'dotted', strong: 'rgba(58,45,29,0.24)', hair: 'rgba(58,45,29,0.24)' },
  radius: { card: '0', control: '0' },
  surface: {
    ownsBackground: true,
    plate: {
      src: '/glaisher-flammarion.png',
      opacity: 0.13,
      filter: 'sepia(0.62) contrast(1.05) saturate(0.85)',
      blend: 'multiply',
      position: 'center 30%',
      size: 'contain',
    },
    texture:
      'radial-gradient(circle at 22% 14%, rgba(168,95,36,0.07), transparent 38%),' +
      'radial-gradient(circle at 84% 86%, rgba(58,45,29,0.05), transparent 42%)',
  },
  chart: {
    series: {
      temp: '#a85f24',
      dew: '#3f5d7a',
      baro: '#3a2d1d',
      humidity: '#4e5a2b',
      wind: '#a64333',
      rain: '#5c7f9a',
      solar: '#b8860b',
      et: 'rgba(58,45,29,0.84)',
    },
    grid: 'rgba(58,45,29,0.24)',
    gridSoft: 'rgba(58,45,29,0.10)',
    axis: 'rgba(58,45,29,0.84)',
    trace: '#a85f24',
    traceShadow: 'rgba(58,45,29,0.35)',
    traceFillOpacity: 0.1,
    traceSecondary: '#3f5d7a',
    gridMinor: 'rgba(110,138,168,0.18)',
    gridMajor: 'rgba(110,138,168,0.32)',
    surface: '#dccfa9',
  },
  dial: { gradOuter: 0.967, gradInner: 0.887, numeral: 0.747, zone: 0.573, needle: 0.66, trendHand: 0.46 },
  gauge: { strokeWidth: 6, bgOpacity: 0.2, shadow: 'none', borderRadius: '0' },
  nav: {
    iconHues: {
      '/': '#a85f24', '/history': '#6b4a7a', '/forecast': '#3f5d7a',
      '/astronomy': '#a85f24', '/map': '#4e5a2b', '/nowcast': '#5c7f9a',
      '/spray': '#4e5a2b',
    },
    indexStyle: 'roman',
    ribbon: ['#a64333', '#d6bd7e', '#3f5d7a'],
  },
  fontScale: 1.0,
};

export default mammoth;

import type { Theme, TypeRole } from './index';

const role = (
  family: string,
  size: number,
  weight: number,
  extra: Partial<TypeRole> = {},
): TypeRole => ({ family, size, weight, ...extra });

const serif = "'IM Fell English', 'IBM Plex Serif', Georgia, serif";
const body = "'IBM Plex Sans', 'Helvetica Neue', sans-serif";
const mono = "'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace";

/**
 * Glaisher's Notebook — paper theme after James Glaisher's 1862
 * ascent.  Values are the FI palette from
 * ``kanfei-phone-sensor/docs/mocks/v1-instrument.jsx``, matching the
 * Android app's ``Tokens.kt`` glaisherColors / glaisherType (rule:
 * when the mock and the tokens file disagree, the mock wins).
 *
 * ``surface.ownsBackground`` is true; the shell/settings PR (PR 4)
 * wires the paper ground and engraving plate to replace the weather
 * background layer.  For now the fields are just declared.
 */
const glaisher: Theme = {
  name: 'glaisher',
  label: "Glaisher's Notebook",
  colors: {
    bg: '#ede2c4',
    bgSecondary: '#e3d4ac',
    bgCard: '#ede2c4',
    bgCardHover: '#e8dcbb',
    text: '#2c2316',
    textSecondary: 'rgba(44,35,22,0.74)',
    textMuted: 'rgba(44,35,22,0.75)',
    accent: '#9a6e2b',
    accentHover: '#845d23',
    accentMuted: 'rgba(154,110,43,0.10)',
    success: '#4a6b34',
    warning: '#9a6e2b',
    danger: '#9c3e2c',
    border: 'rgba(44,35,22,0.22)',
    borderLight: 'rgba(44,35,22,0.12)',
    gaugeTrack: '#e3d4ac',
    gaugeFill: '#9a6e2b',
    tempHot: '#9c3e2c',
    tempCold: '#6e8aa8',
    tempMid: '#4a6b34',
    barometerNeedle: '#9a6e2b',
    windArrow: '#9a6e2b',
    rainBlue: '#6e8aa8',
    humidityGreen: '#4a6b34',
    solarYellow: '#b8893d',
    headerBg: '#2c2316',
    sidebarBg: '#2c2316',
    sky: '#6e8aa8',
    surfaceSunken: '#e3d4ac',
  },
  fonts: { body, heading: serif, mono, gauge: mono, display: serif },
  type: {
    display: role(serif, 104, 400, { italic: true }),
    heading: role(serif, 30, 400, { italic: true }),
    title: role(serif, 17, 400, { italic: true }),
    body: role(body, 14, 400),
    mono: role(mono, 13, 400),
    sectionLabel: role(mono, 10, 500, { tracking: 2, transform: 'uppercase' }),
  },
  rules: { hairline: 1, style: 'solid', strong: 'rgba(44,35,22,0.22)', hair: 'rgba(44,35,22,0.12)' },
  radius: { card: '0', control: '0' },
  surface: {
    ownsBackground: true,
    plate: {
      src: '/glaisher-adieu-1867.png',
      opacity: 0.14,
      filter: 'sepia(0.55) contrast(1.05) saturate(0.9)',
      blend: 'multiply',
      position: 'center 30%',
      size: 'contain',
    },
    texture:
      'radial-gradient(circle at 18% 12%, rgba(154,110,43,0.07), transparent 35%),' +
      'radial-gradient(circle at 85% 88%, rgba(44,35,22,0.05), transparent 40%)',
  },
  chart: {
    series: {
      temp: '#9a6e2b',
      dew: '#3f5d7a',
      baro: '#2c2316',
      humidity: '#4a6b34',
      wind: '#a64333',
      rain: '#5c7f9a',
      solar: '#b8860b',
      et: 'rgba(44,35,22,0.84)',
    },
    grid: 'rgba(44,35,22,0.22)',
    gridSoft: 'rgba(44,35,22,0.10)',
    axis: 'rgba(44,35,22,0.84)',
    trace: '#b8893d',
    traceShadow: 'rgba(44,35,22,0.35)',
    traceFillOpacity: 0.1,
    traceSecondary: '#6e8aa8',
    gridMinor: 'rgba(110,138,168,0.18)',
    gridMajor: 'rgba(110,138,168,0.32)',
    surface: '#e3d4ac',
  },
  dial: { gradOuter: 0.967, gradInner: 0.887, numeral: 0.747, zone: 0.573, needle: 0.66, trendHand: 0.46 },
  gauge: { strokeWidth: 6, bgOpacity: 0.2, shadow: 'none', borderRadius: '0' },
  fontScale: 1.0,
};

export default glaisher;

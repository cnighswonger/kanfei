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
  };
  fonts: {
    body: string;
    heading: string;
    mono: string;
    gauge: string;
  };
  gauge: {
    strokeWidth: number;
    bgOpacity: number;
    shadow: string;
    borderRadius: string;
  };
  /** Global font-size multiplier applied via the `--font-scale` CSS variable.
   *  Editor clamps to 0.85–1.75; 1.0 = preset baseline. */
  fontScale: number;
}

import dark from './dark';
import light from './light';
import classic from './classic';

export const themes: Record<string, Theme> = { dark, light, classic };
export const defaultTheme = 'dark';
export { dark, light, classic };

/** Deep-merge overrides onto a base preset to create a custom theme. */
export function createCustomTheme(base: Theme, overrides: Partial<{
  colors: Partial<Theme['colors']>;
  fonts: Partial<Theme['fonts']>;
  gauge: Partial<Theme['gauge']>;
  fontScale: number;
}>): Theme {
  return {
    name: 'custom',
    label: 'Custom',
    colors: { ...base.colors, ...overrides.colors },
    fonts: { ...base.fonts, ...overrides.fonts },
    gauge: { ...base.gauge, ...overrides.gauge },
    fontScale: overrides.fontScale ?? base.fontScale,
  };
}

import type { Theme } from './index';

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
  },
  fonts: {
    body: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    heading: "Georgia, 'Times New Roman', serif",
    mono: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    gauge: "'Georgia', serif",
  },
  gauge: {
    strokeWidth: 6,
    bgOpacity: 0.2,
    shadow: '0 2px 16px rgba(58,46,30,0.15)',
    borderRadius: '8px',
  },
};

export default classic;

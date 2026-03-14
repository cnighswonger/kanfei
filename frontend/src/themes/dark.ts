import type { Theme } from './index';

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
  },
  fonts: {
    body: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    heading: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    gauge: "'JetBrains Mono', 'Fira Code', monospace",
  },
  gauge: {
    strokeWidth: 8,
    bgOpacity: 0.3,
    shadow: '0 4px 24px rgba(0,0,0,0.4)',
    borderRadius: '16px',
  },
};

export default dark;

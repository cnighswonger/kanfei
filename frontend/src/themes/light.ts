import type { Theme } from './index';

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
  },
  fonts: {
    body: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    heading: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    gauge: "'JetBrains Mono', 'Fira Code', monospace",
  },
  gauge: {
    strokeWidth: 8,
    bgOpacity: 0.15,
    shadow: '0 2px 12px rgba(0,0,0,0.08)',
    borderRadius: '16px',
  },
};

export default light;

/**
 * Weather-synced dynamic background with CSS gradients, particle effects,
 * and optional custom images per scene.
 *
 * Rendering layers (bottom to top):
 *   1. Gradient/image layer (position: fixed)
 *   2. Particle effects layer (rain/snow/stars)
 *   3. Theme color overlay (configurable opacity)
 */

import { useRef, useEffect } from "react";
import { useWeatherScene, type WeatherScene } from "../hooks/useWeatherScene.ts";
import { useWeatherBackground } from "../context/WeatherBackgroundContext.tsx";
import { useTheme } from "../context/ThemeContext.tsx";

// --- CSS Gradients per scene ---

export const SCENE_GRADIENTS: Record<WeatherScene, string> = {
  "clear-day":
    "linear-gradient(180deg, #1e90ff 0%, #87ceeb 35%, #b0e0e6 65%, #87ceeb 100%)",
  "clear-night":
    "linear-gradient(180deg, #0a0e27 0%, #111640 30%, #1a1e50 60%, #0a0e27 100%)",
  dawn:
    "linear-gradient(180deg, #1a1a2e 0%, #16213e 15%, #e96443 40%, #ffc857 70%, #87ceeb 100%)",
  dusk:
    "linear-gradient(180deg, #0d1b2a 0%, #1b2838 15%, #553c7b 40%, #e96443 70%, #ffc857 100%)",
  rain:
    "linear-gradient(180deg, #4a5568 0%, #636e7f 30%, #718096 60%, #a0aec0 100%)",
  "rain-night":
    "linear-gradient(180deg, #1a1d23 0%, #252a33 30%, #2d3748 60%, #1a1d23 100%)",
  storm:
    "linear-gradient(180deg, #0f1318 0%, #1a202c 25%, #2d3748 50%, #1a202c 75%, #0f1318 100%)",
  snow:
    "linear-gradient(180deg, #ccd5e0 0%, #e2e8f0 30%, #edf2f7 60%, #e2e8f0 100%)",
};

// --- Scene labels for Settings UI ---

export const SCENE_LABELS: Record<WeatherScene, string> = {
  "clear-day": "Clear Day",
  "clear-night": "Clear Night",
  dawn: "Dawn",
  dusk: "Dusk",
  rain: "Rain",
  "rain-night": "Rain (Night)",
  storm: "Storm",
  snow: "Snow",
};

export const ALL_SCENES: WeatherScene[] = [
  "clear-day", "clear-night", "dawn", "dusk",
  "rain", "rain-night", "storm", "snow",
];

// --- Which scenes get which particle effect ---

type ParticleEffect = "none" | "rain" | "snow" | "stars" | "storm";

const SCENE_EFFECTS: Record<WeatherScene, ParticleEffect> = {
  "clear-day": "none",
  "clear-night": "stars",
  dawn: "none",
  dusk: "none",
  rain: "rain",
  "rain-night": "rain",
  storm: "storm",
  snow: "snow",
};

// --- Hex to rgba helper ---

function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// CSS properties to make semi-transparent when backgrounds are active
const TRANSLUCENT_PROPS = [
  { prop: "--color-bg-card", key: "bgCard" as const },
  { prop: "--color-bg-card-hover", key: "bgCardHover" as const },
  { prop: "--color-bg-secondary", key: "bgSecondary" as const },
  { prop: "--color-header-bg", key: "headerBg" as const },
  { prop: "--color-sidebar-bg", key: "sidebarBg" as const },
];

// --- Component ---

export default function WeatherBackground() {
  const { enabled, intensity, transparency, customImages } = useWeatherBackground();
  const scene = useWeatherScene();
  const { theme } = useTheme();
  const prevSceneRef = useRef<WeatherScene>(scene);

  // Track previous scene for crossfade
  useEffect(() => {
    prevSceneRef.current = scene;
  }, [scene]);

  // Override card/header/sidebar backgrounds with semi-transparent versions.
  // Also set "--<prop>-solid" companions that remain opaque for SVG fills
  // and chart backgrounds so only container backgrounds become transparent.
  useEffect(() => {
    const root = document.documentElement;
    if (enabled) {
      // Signal to ThemeContext to skip these properties on theme changes
      root.dataset.weatherBg = "active";
      // Transparency 0 → fully opaque (alpha=1); 100 → mostly transparent (alpha=0.3)
      const alpha = 1 - (transparency / 100) * 0.7;
      for (const { prop, key } of TRANSLUCENT_PROPS) {
        root.style.setProperty(prop, hexToRgba(theme.colors[key], alpha));
        root.style.setProperty(`${prop}-solid`, theme.colors[key]);
      }
    } else {
      delete root.dataset.weatherBg;
      // Restore opaque theme colors and remove solid companions
      for (const { prop, key } of TRANSLUCENT_PROPS) {
        root.style.setProperty(prop, theme.colors[key]);
        root.style.removeProperty(`${prop}-solid`);
      }
    }
  }, [enabled, transparency, theme]);

  if (!enabled) return null;

  const overlayOpacity = 1 - intensity / 100;
  const customUrl = customImages[scene];
  const bgStyle = customUrl
    ? `url(${customUrl}) center/cover no-repeat`
    : SCENE_GRADIENTS[scene];
  const effect = SCENE_EFFECTS[scene];

  return (
    <>
      {/* Layer 1: Gradient or custom image */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 0,
          background: bgStyle,
          transition: "background 2s ease",
        }}
      />

      {/* Layer 2: Particle effects */}
      {effect !== "none" && (
        <div
          className={`weather-particles weather-particles--${effect}`}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1,
            pointerEvents: "none",
            overflow: "hidden",
          }}
        />
      )}

      {/* Layer 3: Theme color overlay */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 2,
          backgroundColor: theme.colors.bg,
          opacity: overlayOpacity,
          transition: "opacity 0.5s ease, background-color 0.3s ease",
          pointerEvents: "none",
        }}
      />
    </>
  );
}

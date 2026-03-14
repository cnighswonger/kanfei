/**
 * Context for weather background settings with localStorage persistence.
 *
 * Manages: enabled (on/off), intensity (0-100), and custom images per scene.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { API_BASE } from "../utils/constants.ts";
import { readUIPref, writeUIPref, syncUIPrefs } from "../utils/uiPrefs.ts";

interface WeatherBackgroundContextValue {
  enabled: boolean;
  setEnabled: (v: boolean) => void;
  intensity: number;
  setIntensity: (v: number) => void;
  transparency: number;
  setTransparency: (v: number) => void;
  customImages: Record<string, string>;
  refreshCustomImages: () => void;
}

const WeatherBackgroundContext =
  createContext<WeatherBackgroundContextValue | null>(null);

const PREF_ENABLED = "ui_weather_bg_enabled";
const PREF_INTENSITY = "ui_weather_bg_intensity";
const PREF_TRANSPARENCY = "ui_weather_bg_transparency";

function loadEnabled(): boolean {
  return readUIPref(PREF_ENABLED, "true") !== "false";
}

function loadIntensity(): number {
  const n = parseInt(readUIPref(PREF_INTENSITY, "30"), 10);
  return (!isNaN(n) && n >= 0 && n <= 100) ? n : 30;
}

function loadTransparency(): number {
  const n = parseInt(readUIPref(PREF_TRANSPARENCY, "15"), 10);
  return (!isNaN(n) && n >= 0 && n <= 100) ? n : 15;
}

export function WeatherBackgroundProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [enabled, setEnabledState] = useState(loadEnabled);
  const [intensity, setIntensityState] = useState(loadIntensity);
  const [transparency, setTransparencyState] = useState(loadTransparency);
  const [customImages, setCustomImages] = useState<Record<string, string>>({});

  const setEnabled = useCallback((v: boolean) => {
    setEnabledState(v);
    writeUIPref(PREF_ENABLED, String(v));
  }, []);

  const setIntensity = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(100, v));
    setIntensityState(clamped);
    writeUIPref(PREF_INTENSITY, String(clamped));
  }, []);

  const setTransparency = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(100, v));
    setTransparencyState(clamped);
    writeUIPref(PREF_TRANSPARENCY, String(clamped));
  }, []);

  const refreshCustomImages = useCallback(() => {
    fetch(`${API_BASE}/api/backgrounds`)
      .then((r) => (r.ok ? r.json() : { scenes: {} }))
      .then((data: { scenes: Record<string, string> }) => {
        // Convert scene names to full URLs
        const images: Record<string, string> = {};
        for (const [scene, filename] of Object.entries(data.scenes)) {
          images[scene] = `${API_BASE}/backgrounds/${filename}`;
        }
        setCustomImages(images);
      })
      .catch(() => {
        /* ignore — backgrounds endpoint may not exist yet */
      });
  }, []);

  // Load custom images on mount
  useEffect(() => {
    refreshCustomImages();
  }, [refreshCustomImages]);

  // Reconcile with backend on mount
  useEffect(() => {
    syncUIPrefs().then((prefs) => {
      const e = prefs[PREF_ENABLED];
      if (e !== undefined) {
        const synced = e !== "false";
        setEnabledState((cur) => cur !== synced ? synced : cur);
      }
      const i = prefs[PREF_INTENSITY];
      if (i !== undefined) {
        const n = parseInt(i, 10);
        if (!isNaN(n)) setIntensityState((cur) => cur !== n ? n : cur);
      }
      const t = prefs[PREF_TRANSPARENCY];
      if (t !== undefined) {
        const n = parseInt(t, 10);
        if (!isNaN(n)) setTransparencyState((cur) => cur !== n ? n : cur);
      }
    });
  }, []);

  return (
    <WeatherBackgroundContext.Provider
      value={{
        enabled,
        setEnabled,
        intensity,
        setIntensity,
        transparency,
        setTransparency,
        customImages,
        refreshCustomImages,
      }}
    >
      {children}
    </WeatherBackgroundContext.Provider>
  );
}

export function useWeatherBackground(): WeatherBackgroundContextValue {
  const ctx = useContext(WeatherBackgroundContext);
  if (ctx === null) {
    throw new Error(
      "useWeatherBackground must be used within a WeatherBackgroundProvider",
    );
  }
  return ctx;
}

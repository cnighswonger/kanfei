/**
 * Determines the current weather scene from live sensor data and astronomy.
 *
 * Scenes (priority order): storm > snow > rain/rain-night > dawn > dusk > clear-day > clear-night
 */

import { useMemo } from "react";
import { useWeatherData } from "../context/WeatherDataContext.tsx";

export type WeatherScene =
  | "clear-day"
  | "clear-night"
  | "dawn"
  | "dusk"
  | "rain"
  | "rain-night"
  | "storm"
  | "snow";

/**
 * Parse a time string like "6:42 AM" or "12:05 PM" into today's Date.
 * Returns null for "--" or unparseable strings.
 */
function parseTimeToday(timeStr: string | undefined): Date | null {
  if (!timeStr || timeStr === "--") return null;

  const match = timeStr.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return null;

  let hour = parseInt(match[1], 10);
  const minute = parseInt(match[2], 10);
  const ampm = match[3].toUpperCase();

  if (ampm === "PM" && hour !== 12) hour += 12;
  if (ampm === "AM" && hour === 12) hour = 0;

  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate(), hour, minute);
}

export function useWeatherScene(): WeatherScene {
  const { currentConditions, astronomy } = useWeatherData();

  return useMemo(() => {
    const now = new Date();

    // Parse astronomy times
    const sunrise = parseTimeToday(astronomy?.sun.sunrise);
    const sunset = parseTimeToday(astronomy?.sun.sunset);
    const civilDawn = parseTimeToday(astronomy?.sun.civil_twilight.dawn);
    const civilDusk = parseTimeToday(astronomy?.sun.civil_twilight.dusk);

    // Determine time-of-day
    const isDaytime =
      sunrise && sunset ? now >= sunrise && now <= sunset : now.getHours() >= 6 && now.getHours() < 20;
    const isDawn =
      civilDawn && sunrise ? now >= civilDawn && now < sunrise : false;
    const isDusk =
      sunset && civilDusk ? now > sunset && now <= civilDusk : false;

    // Weather conditions
    const rainRate = currentConditions?.rain?.rate?.value ?? 0;
    const isRaining = rainRate > 0;
    const windSpeed = currentConditions?.wind?.speed?.value ?? 0;
    const barometerTrend = currentConditions?.barometer?.trend;
    const trendRate = currentConditions?.barometer?.trend_rate ?? 0;
    const outsideTemp = currentConditions?.temperature?.outside?.value ?? 50;

    const isStormy = windSpeed > 30 || (barometerTrend === "falling" && trendRate < -0.06);
    const isFreezing = outsideTemp < 32;

    // Priority-based selection
    if (isStormy) return "storm";
    if (isRaining && isFreezing) return "snow";
    if (isRaining && isDaytime) return "rain";
    if (isRaining) return "rain-night";
    if (isDawn) return "dawn";
    if (isDusk) return "dusk";
    if (isDaytime) return "clear-day";
    return "clear-night";
  }, [currentConditions, astronomy]);
}

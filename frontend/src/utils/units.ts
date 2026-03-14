// ============================================================
// Unit conversion and formatting utilities for weather values.
// ============================================================

// --- Temperature ---

export function fahrenheitToCelsius(f: number): number {
  return ((f - 32) * 5) / 9;
}

export function celsiusToFahrenheit(c: number): number {
  return (c * 9) / 5 + 32;
}

// --- Pressure ---

export function inHgToHpa(inHg: number): number {
  return inHg * 33.8639;
}

export function hpaToInHg(hPa: number): number {
  return hPa / 33.8639;
}

// --- Wind speed ---

export function mphToKph(mph: number): number {
  return mph * 1.60934;
}

export function kphToMph(kph: number): number {
  return kph / 1.60934;
}

export function mphToKnots(mph: number): number {
  return mph * 0.868976;
}

// --- Precipitation ---

export function inchesToMm(inches: number): number {
  return inches * 25.4;
}

export function mmToInches(mm: number): number {
  return mm / 25.4;
}

// --- Display formatters ---

/**
 * Converts a temperature stored as tenths-of-a-degree Fahrenheit into a
 * human-readable string in the requested unit.
 *
 * Example: formatTemp(725, "F") => "72.5"
 */
export function formatTemp(tenthsF: number, unit: "F" | "C" = "F"): string {
  const degF = tenthsF / 10;
  if (unit === "C") {
    return fahrenheitToCelsius(degF).toFixed(1);
  }
  return degF.toFixed(1);
}

/**
 * Converts a barometric pressure stored as thousandths-of-an-inch-Hg into a
 * human-readable string in the requested unit.
 *
 * Example: formatPressure(30125, "inHg") => "30.125"
 */
export function formatPressure(
  thousandthsInHg: number,
  unit: "inHg" | "hPa" = "inHg",
): string {
  const inHg = thousandthsInHg / 1000;
  if (unit === "hPa") {
    return inHgToHpa(inHg).toFixed(1);
  }
  return inHg.toFixed(3);
}

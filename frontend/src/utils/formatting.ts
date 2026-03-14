// ============================================================
// Display formatting utilities for the weather dashboard.
// ============================================================

/**
 * Formats an ISO-8601 timestamp string as a short time (e.g. "3:45 PM").
 */
export function formatTimestamp(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

/**
 * Formats an ISO-8601 date string as a short date (e.g. "Feb 15, 2026").
 */
export function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Formats a duration in seconds as a compact human string.
 *
 * Examples:
 *   formatDuration(135)   => "2m 15s"
 *   formatDuration(8100)  => "2h 15m"
 *   formatDuration(90061) => "1d 1h"
 */
export function formatDuration(seconds: number): string {
  if (seconds < 0) seconds = 0;

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (days > 0) {
    return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  }
  if (hours > 0) {
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  }
  if (minutes > 0) {
    return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
  }
  return `${secs}s`;
}

/**
 * Converts a compass bearing (0-360) to a 16-point cardinal direction string.
 */
export function cardinalDirection(degrees: number): string {
  const DIRECTIONS = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
  ] as const;

  // Normalise to 0-360 range
  const norm = ((degrees % 360) + 360) % 360;
  const index = Math.round(norm / 22.5) % 16;
  return DIRECTIONS[index];
}

/**
 * Returns a Unicode arrow character representing a barometric trend.
 */
export function trendArrow(
  trend: "rising" | "falling" | "steady" | null,
): string {
  switch (trend) {
    case "rising":
      return "\u2191"; // up arrow
    case "falling":
      return "\u2193"; // down arrow
    case "steady":
      return "\u2192"; // right arrow (steady)
    default:
      return "";
  }
}

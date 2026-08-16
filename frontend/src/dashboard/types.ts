/**
 * The one adapter point.
 *
 * Every dashboard tile reads from this shape and nothing else — no API calls, no
 * context, no hooks inside tiles. Map your live weather payload into this once,
 * in `Dashboard.tsx`, and the layout is done.
 *
 * Field names are ours, not the API's. If a value isn't available yet, pass
 * `null` — every tile renders an em-dash for null rather than crashing or showing
 * a zero, which is what makes a partially-wired dashboard still look right.
 */

export interface Reading {
  value: number | null;
  /** Pre-formatted for display when the raw number needs unit-aware rounding. */
  text?: string;
}

export interface DashboardData {
  station: {
    name: string;          // 'Sanford, NC'
    elevationFt: number | null;
    intervalSeconds: number | null;   // 10
    clock: string;         // '14:41:03'
    lastPoll: string;      // '2:41:05 PM'
    console: string;       // 'Vantage Vue'
    model: string;         // '6351'
    firmware: string;      // '1.90'
    transmittersOk: boolean;
    batteryVolts: number | null;
    crcErrors: number;
    timeouts: number;
    archiveRecords: number | null;
    /** App version for the footer, e.g. '1.0.0'. */
    appVersion?: string | null;
  };

  outside: {
    tempF: number | null;
    feelsLikeF: number | null;
    heatIndexF: number | null;
    windChillF: number | null;
    dewPointF: number | null;
    thetaEK: number | null;
    humidityPct: number | null;
    insideTempF: number | null;
    insideHumidityPct: number | null;
    highF: number | null;
    highAt: string | null;   // '3:12 PM'
    lowF: number | null;
    lowAt: string | null;
  };

  barometer: {
    inHg: number | null;
    hPa: number | null;
    trendInHgPer3h: number | null;   // signed
    zone: string | null;             // 'FAIR'
    todayHigh: number | null;
    todayHighAt: string | null;
    todayLow: number | null;
    todayLowAt: string | null;
  };

  wind: {
    speedMph: number | null;
    directionDeg: number | null;
    directionLabel: string | null;   // 'WSW'
    gustMph: number | null;
    peakMph: number | null;
    peakAt: string | null;
    /** 16 normalised sector weights, max 1. Omit and the rose is hidden. */
    roseWeights?: number[];
  };

  rain: {
    rateInPerHr: number | null;
    todayIn: number | null;
    yesterdayIn: number | null;
    yearIn: number | null;
    /** 24 hourly totals in inches, oldest first. */
    hourlyIn: (number | null)[];
  };

  solar: {
    wm2: number | null;
    uvIndex: number | null;
    energyMJ: number | null;
    etIn: number | null;
  };

  forecast: {
    /** Zambretti sentence, e.g. 'Fairly fine, becoming less settled.' */
    zambretti: string | null;
    confidencePct: number | null;
  };

  almanac: {
    sunrise: string | null;      // '6:24 AM'
    sunset: string | null;       // '8:03 PM'
    dayLength: string | null;    // '13h 39m'  — always positive
    dayLengthDelta: string | null; // '−1m 12s'
    moonPhase: string | null;    // 'Waxing gibbous'
    moonIlluminationPct: number | null;
  };

  /** 24 h series for the history chart, oldest first. Same length for both. */
  history: {
    tempF: (number | null)[];
    dewPointF: (number | null)[];
    sampleCount: number | null;
    avgTempF: number | null;
  };
}

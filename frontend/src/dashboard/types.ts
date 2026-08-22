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

/**
 * Resolution buttons on the Weather Nerd multi-series chart.  Labels are
 * user-facing — the adapter maps them to the backend's ``raw`` / ``5m`` /
 * ``hourly`` / ``daily`` query values before hitting ``/api/history``.
 */
export type NerdResolution = 'Raw' | '5 min' | 'Hourly' | 'Daily';

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
    lastPoll: string;      // 24-hour 'HH:MM', formatted in the adapter
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
    /**
     * Provenance for ``yearIn``.  ``'console'`` = raw Vue counter;
     * ``'archive'`` = summed from stored daily rain since the season
     * boundary because a mid-year console reset was detected.  See
     * backend ``services/rain_year.py``.  Displayed inline next to
     * the Year figure so an operator reading the value can tell
     * where it came from — Design v41.
     */
    yearSource?: "console" | "archive";
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

  /**
   * Agriculture persona only (mock 3c). Omit for Everyday and Weather nerd —
   * `AgricultureDashboard` renders an em-dash state when it's absent.
   *
   * Field names follow backend/app/models/spray.py so the UI can show the same
   * reason strings the API returns.
   */
  spray?: {
    product: { name: string; category: string | null } | null;
    /** Verdict from spray_engine.py: all checks pass, some fail, or near a limit. */
    verdict: 'go' | 'marginal' | 'nogo' | null;
    verdictNote: string | null;      // 'All four checks pass right now'
    caution: string | null;          // 'Window closes 6:40 PM — wind rising'
    /** One row per check. `name` matches the backend: wind|temperature|humidity|rain_free */
    checks: {
      name: string;
      label: string;                 // 'Wind'
      value: string;                 // '7.0'
      limit: string;                 // '≤ 10 mph'
      pass: boolean;
    }[];
    /** 24 hourly cells, from scoreSprayHours() in utils/gauges.ts */
    window: { hour: number; label: string; state: 'go' | 'marginal' | 'nogo' }[];
    bestWindowToday: string | null;  // '2:40 – 6:40 PM'
    nextWindow: string | null;       // 'Tomorrow 7:10 AM'
    /** Gust frequency histogram, 2 mph bins, last 4 h. */
    gustBins: number[];
    water: {
      balanceIn: number | null;      // rain − ET over 7 days, signed
      rainTodayIn: number | null;
      rainWeekIn: number | null;
      etTodayIn: number | null;
      etWeekIn: number | null;
      etMonthIn: number | null;
      etYearIn: number | null;
      seasonRainIn: number | null;
    };
    schedule: { product: string; when: string; status: 'go' | 'pending' | 'nogo' }[];
    applications: { product: string; date: string; stars: number; note: string | null }[];
    driftRatePct: number | null;
  };

  /**
   * Weather nerd persona only (mock 2b). Omit and every tile renders em-dashes.
   *
   * Almost all of this already exists server-side — it's re-exposure, not new
   * physics. Marked NEW where a value genuinely has to be computed or stored.
   */
  nerd?: {
    // ── pressure provenance (from the same barometer read) ──────────────────
    altimeterInHg: number | null;
    seaLevelHPa: number | null;

    // ── theta-e provenance ─────────────────────────────────────────────────
    /** NEW: theta-e now minus theta-e at 06Z. Needs one stored value per day. */
    thetaEDelta: number | null;
    mixingRatioGKg: number | null;
    /** Lifted condensation level, ft AGL. */
    lclFt: number | null;

    // ── forecast agreement ─────────────────────────────────────────────────
    nwsAgrees: boolean | null;
    /** NEW: % of the last 30 days Zambretti and NWS agreed. Needs a daily log. */
    agreementRate30d: number | null;

    // ── link quality ───────────────────────────────────────────────────────
    reception: {
      /**
       * Link quality over `windowLabel`. Must be computed over the SAME window
       * as the counters below — a percentage from one window beside counts
       * from another is unreadable.
       */
      pct: number | null;
      received: number | null;
      missed: number | null;
      crcErrors: number | null;
      resyncs: number | null;
      /**
       * The window these figures cover, e.g. "last hour" or "since midnight".
       * The tile renders it in the kicker so a small received-count is legible
       * instead of alarming.
       */
      windowLabel: string | null;
    } | null;

    // ── chart ──────────────────────────────────────────────────────────────
    /** 24 h pressure series, same length as history.tempF. Own right axis. */
    historyInHg: (number | null)[];
    /** Which resolution button is active. */
    resolution: NerdResolution | null;

    // ── solar ──────────────────────────────────────────────────────────────
    /** Daily solar energy MJ/m², oldest first, 14 entries. Today is last. */
    solarEnergy14d: (number | null)[];

    // ── console extremes (the console already tracks all of these) ──────────
    extremes: {
      tempDayHigh: number | null;  tempDayLow: number | null;
      tempMonthHigh: number | null; tempMonthLow: number | null;
      baroDayHigh: number | null;  baroDayLow: number | null;
      baroYearHigh: number | null; baroYearLow: number | null;
      gustMonthMax: number | null;
      rainYearIn: number | null;
    } | null;

    // ── calibration ────────────────────────────────────────────────────────
    /** The configured barometer offset, signed, inHg. */
    baroOffsetInHg: number | null;
    /** NEW: live delta against a reference station's altimeter setting. */
    baroVsReferenceInHg: number | null;
    /** ICAO id of that station, e.g. 'KTTA'. */
    referenceStation: string | null;

    // ── system footer ──────────────────────────────────────────────────────
    metar: string | null;
    dbSizeMB: number | null;
    /** e.g. 'WU + CWOP' — omit the word 'uploading', the tile adds it. */
    uploadTargets: string | null;
    /** e.g. 'IPC 6514 up' */
    ipcStatus: string | null;
  };
}

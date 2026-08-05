/**
 * The console's own daily extremes, shown against Kanfei's.
 *
 * The point is the comparison, not the numbers. Kanfei's extremes come
 * from 10-second polls; the console samples continuously, so it catches
 * a gust or a spike that fell between our polls. Where the two differ,
 * the difference bounds what our sampling misses — which is the class of
 * problem behind #230, where a poisoned daily maximum survived all day
 * before anyone noticed.
 *
 * Read-only. Clearing the console's highs and lows is destructive and
 * lives nowhere near this panel.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  fetchConsoleHighsLows,
  fetchCurrentConditions,
} from "../../api/client.ts";
import type {
  ConsoleHighsLows as ConsoleHighsLowsData,
  CurrentConditions,
  ExtremeReading,
} from "../../api/types.ts";

type LoadStatus = "loading" | "loaded" | "error" | "unsupported";

const card: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  marginBottom: "16px",
};

const title: React.CSSProperties = {
  margin: "0 0 16px 0",
  fontSize: "calc(18px * var(--font-scale))",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const body: React.CSSProperties = {
  fontSize: "calc(13px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  lineHeight: 1.5,
};

const mono: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "calc(12px * var(--font-scale))",
};

const th: React.CSSProperties = {
  ...body,
  textAlign: "left",
  padding: "4px 10px 4px 0",
  fontWeight: 400,
  opacity: 0.75,
};

const td: React.CSSProperties = {
  ...mono,
  padding: "4px 10px 4px 0",
  color: "var(--color-text)",
  whiteSpace: "nowrap",
};

function fmt(value: number | null | undefined, digits = 1): string {
  return value == null ? "—" : value.toFixed(digits);
}

/** Rows the console and Kanfei both track, so a comparison is possible.
 *
 * The two sources do NOT agree on units: the HILOWS endpoint returns SI
 * (°C, m/s, hPa) straight from the parser, while `daily_extremes` has
 * already been through Kanfei's display conversion and arrives as °F,
 * mph, inHg. Showing 33.2 beside 91.8 for the same temperature would be
 * worse than showing nothing, so each row converts the console value into
 * whatever unit Kanfei reported and displays that unit.
 */
interface Row {
  label: string;
  digits: number;
  /** SI -> the unit `daily_extremes` uses for this reading. */
  toKanfeiUnits: (si: number) => number;
  /** Fallback label when Kanfei has no reading to take the unit from. */
  fallbackUnit: string;
  consoleHigh: (d: ConsoleHighsLowsData) => number | null;
  consoleLow: (d: ConsoleHighsLowsData) => number | null;
  consoleHighTime: (d: ConsoleHighsLowsData) => string | null;
  kanfeiHigh: (c: CurrentConditions) => ExtremeReading | null;
  kanfeiLow: (c: CurrentConditions) => ExtremeReading | null;
}

// These assume `daily_extremes` always reports F/mph/inHg, which is true
// today because /api/current converts with fixed units.  If per-user unit
// preferences are ever wired into that endpoint, this panel is where they
// break: it takes the LABEL from Kanfei's reading but converts to a fixed
// target, so a station set to metric would show "33.2 C" labelled from
// Kanfei and "91.8 C" converted here.  Convert to the reported unit at
// that point rather than to a constant.  (Codex, #268 R1.)
const cToF = (c: number) => c * 9 / 5 + 32;
const msToMph = (ms: number) => ms * 2.236936;
const hpaToInhg = (hpa: number) => hpa * 0.029529983071445;

const ROWS: Row[] = [
  {
    label: "Outside temperature",
    digits: 1,
    toKanfeiUnits: cToF,
    fallbackUnit: "F",
    consoleHigh: (d) => d.outside_temp.day.high,
    consoleLow: (d) => d.outside_temp.day.low,
    consoleHighTime: (d) => d.outside_temp.day.time_high,
    kanfeiHigh: (c) => c.daily_extremes?.outside_temp_hi ?? null,
    kanfeiLow: (c) => c.daily_extremes?.outside_temp_lo ?? null,
  },
  {
    label: "Wind speed",
    digits: 1,
    toKanfeiUnits: msToMph,
    fallbackUnit: "mph",
    consoleHigh: (d) => d.wind_speed.day.value,
    consoleLow: () => null,
    consoleHighTime: (d) => d.wind_speed.day.time,
    kanfeiHigh: (c) => c.daily_extremes?.wind_speed_hi ?? null,
    kanfeiLow: () => null,
  },
  {
    label: "Barometer",
    digits: 2,
    toKanfeiUnits: hpaToInhg,
    fallbackUnit: "inHg",
    consoleHigh: (d) => d.barometer.day.high,
    consoleLow: (d) => d.barometer.day.low,
    consoleHighTime: (d) => d.barometer.day.time_high,
    kanfeiHigh: (c) => c.daily_extremes?.barometer_hi ?? null,
    kanfeiLow: (c) => c.daily_extremes?.barometer_lo ?? null,
  },
  {
    label: "Outside humidity",
    digits: 0,
    toKanfeiUnits: (v) => v,
    fallbackUnit: "%",
    // humidities[0] is the outside sensor; 1-7 are the extras. The array
    // is empty when the block could not be parsed, so guard the index.
    consoleHigh: (d) => d.humidities?.[0]?.day.high ?? null,
    consoleLow: (d) => d.humidities?.[0]?.day.low ?? null,
    consoleHighTime: (d) => d.humidities?.[0]?.day.time_high ?? null,
    kanfeiHigh: (c) => c.daily_extremes?.humidity_hi ?? null,
    kanfeiLow: (c) => c.daily_extremes?.humidity_lo ?? null,
  },
];


interface Props {
  supported: boolean;
  isMobile: boolean;
}

export default function ConsoleHighsLows({ supported, isMobile }: Props) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [data, setData] = useState<ConsoleHighsLowsData | null>(null);
  const [ours, setOurs] = useState<CurrentConditions | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const [console_, current] = await Promise.all([
        fetchConsoleHighsLows(),
        // Non-fatal: without it the console column still stands alone,
        // which is worth more than failing the whole panel.
        fetchCurrentConditions().catch(() => null),
      ]);
      setData(console_.highs_lows);
      setOurs(current);
      setStatus("loaded");
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        setStatus("unsupported");
        return;
      }
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
    }
  }, []);

  useEffect(() => {
    if (supported) void load();
    else setStatus("unsupported");
  }, [supported, load]);

  if (status === "unsupported") return null;

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={title}>Console Highs &amp; Lows</h3>

      <p style={{ ...body, marginTop: 0 }}>
        Today's extremes as the console recorded them. It samples
        continuously; Kanfei records every {" "}
        <span style={mono}>10 s</span>, so the console may have caught a
        peak that fell between readings. A large difference means our
        sampling missed something.
      </p>

      {status === "loading" && <p style={body}>Reading the console…</p>}
      {status === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read highs and lows: {error}
        </p>
      )}

      {status === "loaded" && data && (
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", minWidth: "34em" }}>
            <thead>
              <tr>
                <th style={th}></th>
                <th style={th}>Console high</th>
                <th style={th}>at</th>
                <th style={th}>Kanfei high</th>
                <th style={th}>Console low</th>
                <th style={th}>Kanfei low</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => {
                const kHi = ours ? row.kanfeiHigh(ours) : null;
                const kLo = ours ? row.kanfeiLow(ours) : null;
                // Take the unit from whichever side reported one, so the
                // label always describes the numbers beside it.
                const unit = kHi?.unit ?? kLo?.unit ?? row.fallbackUnit;
                const rawHi = row.consoleHigh(data);
                const rawLo = row.consoleLow(data);
                const cHi = rawHi == null ? null : row.toKanfeiUnits(rawHi);
                const cLo = rawLo == null ? null : row.toKanfeiUnits(rawLo);
                return (
                  <tr key={row.label}>
                    <td style={{ ...td, ...body, color: "var(--color-text-secondary)" }}>
                      {row.label}
                    </td>
                    <td style={td}>
                      {fmt(cHi, row.digits)} {cHi != null && unit}
                    </td>
                    <td style={{ ...td, opacity: 0.7 }}>
                      {row.consoleHighTime(data) ?? "—"}
                    </td>
                    <td style={td}>
                      {fmt(kHi?.value ?? null, row.digits)} {kHi != null && unit}
                    </td>
                    <td style={td}>
                      {fmt(cLo, row.digits)} {cLo != null && unit}
                    </td>
                    <td style={td}>
                      {fmt(kLo?.value ?? null, row.digits)} {kLo != null && unit}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          {!ours && (
            <p style={{ ...body, marginTop: "10px" }}>
              Kanfei's own extremes could not be loaded, so only the
              console column is shown.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

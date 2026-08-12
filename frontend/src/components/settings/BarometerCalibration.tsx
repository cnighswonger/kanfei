/**
 * Barometer calibration for Vantage consoles.
 *
 * The console displays an Altimeter Setting (reduction method 1), which is
 * the same quantity a METAR reports in its Axxxx group — so the reference
 * list and the console reading are directly comparable with no conversion.
 *
 * Calibration is a single BAR= write carrying BOTH a pressure and an
 * elevation.  Two consequences shape this UI: elevation is restated at the
 * moment of commitment rather than only in a field above, and a *failed*
 * write cannot be reported as "nothing changed" — a console that refuses
 * the pressure still applies the elevation (measured on fw 3.0, #252).  On
 * any outcome where the console may have been touched, the panel re-reads
 * BARDATA and shows what the station actually says.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchBarometerCalibration,
  fetchBarometerReference,
  setBarometerCalibration,
} from "../../api/client.ts";
import type {
  BarometerAggregate,
  BarometerCalibrationState,
  BarometerSnapshot,
} from "../../api/types.ts";
import BaroCalibrationAggregate from "./BaroCalibrationAggregate.tsx";

// Mirrors VantageDriver.ELEVATION_MIN_FT / MAX_FT.  Checked here so an
// out-of-range elevation never costs a round trip to be told 400.  The
// BAR pressure bounds used to be validated here too; the aggregate
// panel now owns the pressure value (median-of-medians, gated) so
// front-side range-checking on that side is unnecessary — a
// median-of-medians outside 20-32.5 inHg would signal upstream sensor
// failure long before it reached this panel.
const ELEVATION_MIN_FT = -2_000;
const ELEVATION_MAX_FT = 15_000;

// The console's raw pressure drifts while the panel sits open, and BAR=
// back-solves against whatever it reads at write time.
const SNAPSHOT_MAX_AGE_MINUTES = 10;

const INHG_PER_HPA = 0.029529983071445;

// Pressure falls about 1 hPa per 27 ft near sea level, so a foot of
// elevation error is ~0.001 inHg — the console's own display resolution.
// Used to state a discrepancy in the units being calibrated rather than
// leaving the user to judge whether a difference in feet matters.
const INHG_PER_FOOT = (1 / 27) * INHG_PER_HPA;

type LoadStatus = "loading" | "loaded" | "error";

interface Outcome {
  kind: "success" | "failure";
  message: string;
  before: BarometerSnapshot | null;
  intendedBar: number | null;
  intendedElevation: number | null;
  actual: BarometerSnapshot | null;
  /** False when the re-read after a failure itself failed. */
  actualKnown: boolean;
}

/** Minutes since an ISO timestamp, recomputed on a tick by the caller. */
function minutesSince(iso: string, now: number): number {
  return (now - new Date(iso).getTime()) / 60_000;
}

function formatAge(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.floor(minutes)} min ago`;
  const h = Math.floor(minutes / 60);
  return `${h}h ${Math.floor(minutes % 60)}m ago`;
}

function fmtInhg(v: number | null | undefined): string {
  return v == null ? "—" : v.toFixed(3);
}

function fmtSnapshot(s: BarometerSnapshot | null): string {
  if (!s) return "unknown";
  return `${fmtInhg(s.barometer_inhg)} inHg · ${s.elevation_ft ?? "—"} ft · offset ${fmtInhg(s.barcal_inhg)}`;
}

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

const label: React.CSSProperties = {
  fontSize: "calc(13px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "6px",
  display: "block",
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

const input: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "calc(14px * var(--font-scale))",
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  boxSizing: "border-box",
};

function button(variant: "primary" | "secondary", disabled: boolean): React.CSSProperties {
  return {
    fontFamily: "var(--font-body)",
    fontSize: "calc(14px * var(--font-scale))",
    padding: "9px 18px",
    borderRadius: "6px",
    border: variant === "primary" ? "none" : "1px solid var(--color-border)",
    background: variant === "primary" ? "var(--color-accent)" : "var(--color-bg-secondary)",
    color: variant === "primary" ? "#fff" : "var(--color-text)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
  };
}

interface Props {
  supported: boolean;
  isMobile: boolean;
  /** Kanfei's configured elevation, for the reconcile row. 0 = unset. */
  configElevationFt: number;
}

export default function BarometerCalibration({
  supported,
  isMobile,
  configElevationFt,
}: Props) {
  const [calStatus, setCalStatus] = useState<LoadStatus>("loading");
  const [cal, setCal] = useState<BarometerCalibrationState | null>(null);
  const [calError, setCalError] = useState<string | null>(null);
  const [calFetchedAt, setCalFetchedAt] = useState<string | null>(null);

  const [refStatus, setRefStatus] = useState<LoadStatus>("loading");
  const [aggregate, setAggregate] = useState<BarometerAggregate | null>(null);
  const [locationConfigured, setLocationConfigured] = useState(true);
  const [refError, setRefError] = useState<string | null>(null);

  const [elevationFt, setElevationFt] = useState<string>("");
  const [applying, setApplying] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Drives the age readouts; ages must move while the panel sits open, so
  // they cannot come from the server.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const elevationTouched = useRef(false);

  const loadCal = useCallback(async () => {
    setCalStatus("loading");
    setCalError(null);
    try {
      const data = await fetchBarometerCalibration();
      setCal(data);
      setCalFetchedAt(new Date().toISOString());
      setCalStatus("loaded");
      // The console's value is what is actually in effect, so it seeds the
      // field — but never overwrite what the user has typed.
      if (!elevationTouched.current && data.elevation_ft != null) {
        setElevationFt(String(data.elevation_ft));
      }
      return data;
    } catch (err) {
      setCalError(err instanceof Error ? err.message : String(err));
      setCalStatus("error");
      return null;
    }
  }, []);

  const loadRefs = useCallback(async () => {
    setRefStatus("loading");
    setRefError(null);
    try {
      const data = await fetchBarometerReference();
      setAggregate(data.aggregate);
      setLocationConfigured(data.location_configured);
      setRefStatus("loaded");
    } catch (err) {
      // Drop the aggregate on failure so the panel does not show a stale
      // recommendation with a fresh-looking layout — a hardware write
      // against a value we cannot vouch for is the exact bug the multi-
      // station gate was built to prevent.
      setAggregate(null);
      setRefError(err instanceof Error ? err.message : String(err));
      setRefStatus("error");
    }
  }, []);

  useEffect(() => {
    if (!supported) return;
    void loadCal();
    void loadRefs();
  }, [supported, loadCal, loadRefs]);

  if (!supported) {
    // An explicit statement rather than blank space: a hidden panel is
    // indistinguishable from a missing feature, which is the complaint
    // recorded in #249.
    return (
      <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={title}>Barometer Calibration</h3>
        <p style={body}>
          This station does not support barometer calibration. It is available
          on Davis Vantage consoles, which accept a calibration command over
          the serial link.
        </p>
      </div>
    );
  }

  const snapshotAgeMin = calFetchedAt ? minutesSince(calFetchedAt, now) : null;
  const snapshotTooOld =
    snapshotAgeMin != null && snapshotAgeMin > SNAPSHOT_MAX_AGE_MINUTES;

  const elevationNum = Number(elevationFt);
  const elevationValid =
    elevationFt.trim() !== "" &&
    Number.isFinite(elevationNum) &&
    elevationNum >= ELEVATION_MIN_FT &&
    elevationNum <= ELEVATION_MAX_FT;

  // Aggregate is the only write path.  The button rides on
  // `recommendation.should_apply` inside `BaroCalibrationAggregate`;
  // the parent only gates on the environment (elevation valid, console
  // snapshot fresh, not currently applying).  When any of those fails
  // the callback is withheld so the button is not rendered — the panel
  // above (elevation input, snapshot age warning) shows why.
  const environmentReady =
    !applying &&
    calStatus === "loaded" &&
    refStatus === "loaded" &&
    locationConfigured &&
    elevationValid &&
    !snapshotTooOld;

  async function write(barThousandths: number, describeAs: string) {
    setApplying(true);
    setOutcome(null);
    const before = cal
      ? {
          barometer_inhg: cal.barometer_inhg,
          elevation_ft: cal.elevation_ft,
          barcal_inhg: cal.barcal_inhg,
        }
      : null;

    try {
      // The console's ELEVATION is whole feet; rounding here rather than
      // in the field keeps the stored config at full precision while the
      // wire gets what BAR= can actually absorb.
      const result = await setBarometerCalibration(
        barThousandths,
        Math.round(elevationNum),
      );
      setOutcome({
        kind: "success",
        message: `${describeAs} applied.`,
        // The response carries a matched before/after pair from one round
        // trip — better than a follow-up read that could catch a drifted
        // value and look like the write missed.
        before: result.before ?? before,
        intendedBar: barThousandths,
        intendedElevation: elevationNum,
        actual: result.after,
        actualKnown: result.after != null,
      });
      await loadCal();
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      const message = err instanceof Error ? err.message : String(err);

      // 400 means the driver rejected the arguments before reaching the
      // wire, so the console was never touched — re-reading would only
      // muddy that with an unrelated fresh snapshot.  Anything else may
      // have landed wholly or partly, including a 504 where the command
      // can still complete after we stop waiting.
      if (status === 400) {
        setOutcome({
          kind: "failure",
          message,
          before,
          intendedBar: barThousandths,
          intendedElevation: elevationNum,
          actual: before,
          actualKnown: true,
        });
      } else {
        const fresh = await loadCal();
        setOutcome({
          kind: "failure",
          message,
          before,
          intendedBar: barThousandths,
          intendedElevation: elevationNum,
          actual: fresh
            ? {
                barometer_inhg: fresh.barometer_inhg,
                elevation_ft: fresh.elevation_ft,
                barcal_inhg: fresh.barcal_inhg,
              }
            : null,
          actualKnown: fresh != null,
        });
      }
    } finally {
      setApplying(false);
    }
  }

  function handleClear() {
    if (!elevationValid || applying) return;
    const ok = window.confirm(
      `Clear the barometer offset?\n\n` +
        `The console will keep its elevation of ${elevationNum} ft and return ` +
        `to its uncalibrated reading. This is not an undo — it does not ` +
        `restore a previous calibration, and it does not reverse an ` +
        `elevation change.`,
    );
    if (ok) void write(0, "Offset clear");
  }

  const gridCols = isMobile ? "1fr" : "1fr 1fr";

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={title}>Barometer Calibration</h3>

      {/* --- Console state --- */}
      {calStatus === "loading" && <p style={body}>Reading the console…</p>}
      {calStatus === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read the console: {calError}
        </p>
      )}
      {calStatus === "loaded" && cal && (
        <div style={{ display: "grid", gridTemplateColumns: gridCols, gap: "12px 24px", marginBottom: "16px" }}>
          <div>
            <span style={label}>Console reads</span>
            <span style={{ ...mono, fontSize: "calc(16px * var(--font-scale))", color: "var(--color-text)" }}>
              {fmtInhg(cal.barometer_inhg)} inHg
            </span>
          </div>
          <div>
            <span style={label}>Current offset</span>
            <span style={{ ...mono, fontSize: "calc(16px * var(--font-scale))", color: "var(--color-text)" }}>
              {fmtInhg(cal.barcal_inhg)} inHg
            </span>
          </div>
        </div>
      )}

      {calStatus === "loaded" && (
        <div style={{ marginBottom: "16px" }}>
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            style={{ ...body, background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--color-accent)" }}
          >
            {showAdvanced ? "Hide" : "Show"} factory constants
          </button>
          {showAdvanced && (
            <p style={{ ...body, marginTop: "8px" }}>
              <span style={mono}>gain {cal?.gain ?? "—"} · offset {cal?.offset ?? "—"}</span>
              <br />
              Read-only sensor constants set at the factory. Despite the name,{" "}
              <em>offset</em> here is not the calibration this panel adjusts —
              that is the "current offset" above.
            </p>
          )}
        </div>
      )}

      {/* --- Multi-station aggregate (#298) --- */}
      {/* This IS the calibration flow now.  The old single-station
          picker below was removed with #305's follow-up: it let an
          operator commit to one nearby METAR at face value, which is
          the exact "silently pin to a wrong number" mode the aggregate
          exists to prevent.  Apply is only reachable when both gates
          (min stations, cross-station-spread) pass. */}
      {locationConfigured && aggregate != null && (
        <BaroCalibrationAggregate
          aggregate={aggregate}
          isMobile={isMobile}
          onApplyRecommendation={
            environmentReady
              ? (target) =>
                  void write(target, "Recommended offset")
              : undefined
          }
        />
      )}

      {/* Loading / error / no-location surfaces for the aggregate fetch. */}
      {!locationConfigured && (
        <p style={body}>
          Set your station's location below before calibrating — nearby
          airport reports are found from your coordinates.
        </p>
      )}
      {locationConfigured && refStatus === "loading" && (
        <p style={body}>Looking up nearby airport reports…</p>
      )}
      {locationConfigured && refStatus === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not fetch reference observations: {refError}
        </p>
      )}
      {locationConfigured && refStatus === "loaded" && aggregate == null && (
        <p style={body}>
          No airport reports with a barometric reading were found nearby.
        </p>
      )}

      {snapshotTooOld && (
        <p style={{ ...body, color: "var(--color-warning)", marginBottom: "12px" }}>
          The console reading above is {formatAge(snapshotAgeMin!)}. Refresh
          before applying.
        </p>
      )}

      {/* --- Elevation --- */}
      <div style={{ marginBottom: "16px", maxWidth: "260px" }}>
        <label style={label} htmlFor="baro-cal-elevation">
          Elevation (feet)
        </label>
        <input
          id="baro-cal-elevation"
          type="number"
          value={elevationFt}
          onChange={(e) => {
            elevationTouched.current = true;
            setElevationFt(e.target.value);
          }}
          style={{ ...input, width: "100%" }}
        />
        {!elevationValid && elevationFt.trim() !== "" && (
          <p style={{ ...body, color: "var(--color-danger)", marginTop: "6px" }}>
            Must be between {ELEVATION_MIN_FT} and {ELEVATION_MAX_FT} ft.
          </p>
        )}
        {configElevationFt > 0 &&
          cal?.elevation_ft != null &&
          Math.round(configElevationFt) !== cal.elevation_ft && (
            <p style={{ ...body, marginTop: "6px" }}>
              Console: {cal.elevation_ft} ft · Kanfei: {Math.round(configElevationFt)} ft
              {" ("}
              {Math.abs(
                (Math.round(configElevationFt) - cal.elevation_ft) * INHG_PER_FOOT,
              ).toFixed(3)}{" "}
              inHg){" "}
              <button
                type="button"
                onClick={() => {
                  elevationTouched.current = true;
                  setElevationFt(String(Math.round(configElevationFt)));
                }}
                style={{ ...body, background: "none", border: "none", padding: 0, cursor: "pointer", color: "var(--color-accent)" }}
              >
                use Kanfei's
              </button>
            </p>
          )}
      </div>

      {/* --- Actions ---
          Apply lives on the aggregate panel now (it appears only when
          both gates pass).  This row keeps the operator escape hatches:
          Clear Offset (return to uncalibrated) and Refresh (re-fetch
          both the console reading and the METAR aggregate). */}
      <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
        <button
          type="button"
          onClick={handleClear}
          disabled={applying || !elevationValid}
          style={button("secondary", applying || !elevationValid)}
        >
          Clear Offset
        </button>
        <button
          type="button"
          onClick={() => {
            // Clear the audit row: leaving it under freshly refreshed
            // readings makes it look like it describes them.
            setOutcome(null);
            void loadCal();
            void loadRefs();
          }}
          disabled={applying}
          style={button("secondary", applying)}
        >
          Refresh
        </button>
        {applying && (
          <span style={body}>Applying…</span>
        )}
      </div>

      {/* --- Outcome --- */}
      {outcome && (
        <div
          style={{
            marginTop: "16px",
            padding: "12px",
            borderRadius: "6px",
            border: `1px solid ${outcome.kind === "success" ? "var(--color-success)" : "var(--color-danger)"}`,
          }}
        >
          <p
            style={{
              ...body,
              color: outcome.kind === "success" ? "var(--color-success)" : "var(--color-danger)",
              marginTop: 0,
            }}
          >
            {outcome.message}
          </p>

          <div style={{ ...mono, color: "var(--color-text-secondary)" }}>
            <div>Before: {fmtSnapshot(outcome.before)}</div>
            <div>
              Intended: {outcome.intendedBar === 0 ? "offset cleared" : `${fmtInhg((outcome.intendedBar ?? 0) / 1000)} inHg`}
              {" · "}
              {outcome.intendedElevation} ft
            </div>
            <div>
              Actual:{" "}
              {outcome.actualKnown
                ? fmtSnapshot(outcome.actual)
                : "could not re-read the console to confirm"}
            </div>
          </div>

          {/* The finding from #252, rendered rather than inferred: a refused
              BAR= still commits its elevation, so a failure that moved the
              elevation must say so outright. */}
          {outcome.kind === "failure" &&
            outcome.actualKnown &&
            outcome.actual?.elevation_ft != null &&
            outcome.before?.elevation_ft != null &&
            outcome.actual.elevation_ft !== outcome.before.elevation_ft && (
              <p style={{ ...body, color: "var(--color-warning)", marginBottom: 0, marginTop: "8px" }}>
                Elevation changed from {outcome.before.elevation_ft} ft to{" "}
                {outcome.actual.elevation_ft} ft even though the calibration
                was refused. The console applies elevation separately from the
                pressure value.
              </p>
            )}
        </div>
      )}
    </div>
  );
}

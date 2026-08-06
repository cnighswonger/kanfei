/**
 * Temperature and humidity calibration for Vantage consoles.
 *
 * The other half of #249. The legacy five-field panel is hidden on a
 * Vantage because its shape does not fit: a Vantage adjusts each sensor
 * separately through EEPROM offsets applied with CALED/CALFIX, and its
 * barometer is a different mechanism entirely (BAR=, its own panel).
 *
 * Offsets are stored in the console's native units — tenths of a degree
 * Fahrenheit, whole percent — but nobody thinks in tenths of a degree
 * Fahrenheit. The inputs are degrees and percent; the conversion happens
 * at the edge, in one place, and the raw stored value is shown alongside
 * so a user comparing against the console's own display can see both.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  clearVantageCalibration,
  fetchVantageCalibration,
  setVantageCalibration,
} from "../../api/client.ts";
import type {
  VantageCalibrationField,
  VantageCalibrationOffsets,
} from "../../api/types.ts";

type LoadStatus = "loading" | "loaded" | "error" | "unsupported";

/** Console range for a one-byte signed offset. */
const OFFSET_MIN = -128;
const OFFSET_MAX = 127;

// Appended to success messages for the console's own onboard sensors.
//
// The EEPROM offset changes at once — which is what this panel shows — but
// the console only folds it into the reading when that sensor next reports
// (serial ref §XIV.1).  Measured on fw 3.0 (#276): inside humidity took
// ~30s, because the onboard sensor reports about once a minute.  Outside
// temperature applied in ~1s in the same test, so the note would be
// misleading there — hence per-field rather than blanket.  The cause is
// most likely onboard-sensor vs transmitter, but that is inference: only
// a transmitter-less unit was available.  The flag is therefore named for
// what was observed, not for why.
//
// Barometer calibration does NOT behave this way — BAR= applies
// immediately — so do not copy this note into that panel.
const APPLY_LAG_NOTE =
  " The console folds this into its reading when the sensor next reports," +
  " so the displayed value may take up to a minute to catch up.";

interface FieldDef {
  key: VantageCalibrationField;
  label: string;
  /** Multiplier from the user's unit to the console's stored integer. */
  perUnit: number;
  unit: string;
  step: number;
  hint: string;
  /**
   * The displayed reading is known to lag this offset — see
   * APPLY_LAG_NOTE.  Named for the observed behaviour rather than a cause:
   * the two fields set here are the console's onboard sensors, which is
   * the likely explanation, but CALFIX sends all four fields and the
   * vendor rule is the broader "data packet for that sensor".  Only a
   * transmitter-less bench unit was available, so the outside fields are
   * untested on a station that actually receives them.  If one is ever
   * seen to lag, set this from the measurement (Codex, #280 R1).
   */
  readingLags?: boolean;
}

const FIELDS: FieldDef[] = [
  {
    key: "outside_temp",
    label: "Outside temperature",
    perUnit: 10,
    unit: "°F",
    step: 0.1,
    hint: "Verified on hardware (fw 2.12 and fw 3.0): writing 2.5 °F moved the reading by 2.5 °F.",
  },
  {
    key: "inside_temp",
    label: "Inside temperature",
    perUnit: 10,
    unit: "°F",
    step: 0.1,
    hint: "",
    readingLags: true,
  },
  {
    key: "outside_humidity",
    label: "Outside humidity",
    perUnit: 1,
    unit: "%",
    step: 1,
    hint: "",
  },
  {
    key: "inside_humidity",
    label: "Inside humidity",
    perUnit: 1,
    unit: "%",
    step: 1,
    hint: "",
    readingLags: true,
  },
];

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

const input: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "calc(14px * var(--font-scale))",
  padding: "7px 10px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  width: "7em",
  boxSizing: "border-box",
};

function button(variant: "primary" | "secondary", disabled: boolean): React.CSSProperties {
  return {
    fontFamily: "var(--font-body)",
    fontSize: "calc(13px * var(--font-scale))",
    padding: "7px 14px",
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
}

export default function VantageCalibration({ supported, isMobile }: Props) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [offsets, setOffsets] = useState<VantageCalibrationOffsets>({});
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<{ kind: "ok" | "fail"; text: string } | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const data = await fetchVantageCalibration();
      setOffsets(data.offsets);
      setDrafts({});
      setStatus("loaded");
      return data.offsets;
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        setStatus("unsupported");
        return null;
      }
      setError(err instanceof Error ? err.message : String(err));
      setStatus("error");
      return null;
    }
  }, []);

  useEffect(() => {
    if (supported) void load();
    else setStatus("unsupported");
  }, [supported, load]);

  if (status === "unsupported") {
    // Explicit, not blank: this is the panel #249 says a Vantage user
    // goes looking for, so silence would read as a missing feature.
    return (
      <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={title}>Sensor Calibration</h3>
        <p style={body}>
          This station does not support per-sensor calibration offsets.
        </p>
      </div>
    );
  }

  async function apply(field: FieldDef) {
    const raw = drafts[field.key];
    if (raw === undefined || raw.trim() === "") return;

    const value = Number(raw);
    if (!Number.isFinite(value)) return;

    const stored = Math.round(value * field.perUnit);
    if (stored < OFFSET_MIN || stored > OFFSET_MAX) {
      setOutcome({
        kind: "fail",
        text:
          `${(OFFSET_MIN / field.perUnit).toFixed(field.perUnit === 10 ? 1 : 0)}` +
          ` to ${(OFFSET_MAX / field.perUnit).toFixed(field.perUnit === 10 ? 1 : 0)}` +
          ` ${field.unit} is the range the console accepts.`,
      });
      return;
    }

    setBusy(field.key);
    setOutcome(null);
    try {
      const result = await setVantageCalibration(field.key, stored);
      const applied = result.after?.[field.key];
      setOutcome({
        kind: "ok",
        text:
          applied === undefined
            ? `${field.label} written, but the console could not be re-read.`
            : `${field.label} set to ${(applied / field.perUnit).toFixed(
                field.perUnit === 10 ? 1 : 0,
              )} ${field.unit}.` + (field.readingLags ? APPLY_LAG_NOTE : ""),
      });
      if (result.after) setOffsets(result.after);
      setDrafts((d) => ({ ...d, [field.key]: "" }));
    } catch (err) {
      // The write may or may not have landed; re-read rather than
      // asserting the console is unchanged (#252).
      const message = err instanceof Error ? err.message : String(err);
      await load();
      setOutcome({ kind: "fail", text: message });
    } finally {
      setBusy(null);
    }
  }

  async function clearAll() {
    const ok = window.confirm(
      "Clear every temperature and humidity offset?\n\n" +
        "This zeroes all four sensor calibrations at once and cannot be " +
        "undone. It does NOT affect barometer calibration, which is a " +
        "separate setting.",
    );
    if (!ok) return;

    setBusy("__clear__");
    setOutcome(null);
    try {
      const result = await clearVantageCalibration();
      if (result.after) setOffsets(result.after);
      // clearAll touches every field, including the onboard sensors.
      setOutcome({
        kind: "ok",
        text: "All sensor offsets cleared." + APPLY_LAG_NOTE,
      });
      setDrafts({});
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await load();
      setOutcome({ kind: "fail", text: message });
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={title}>Sensor Calibration</h3>

      <p style={{ ...body, marginTop: 0 }}>
        Offsets added to each sensor's raw reading. The barometer is
        calibrated separately, above.
      </p>

      {status === "loading" && <p style={body}>Reading the console…</p>}
      {status === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read calibration: {error}
        </p>
      )}

      {status === "loaded" && (
        <>
          <div style={{ display: "grid", gap: "10px", marginBottom: "14px" }}>
            {FIELDS.map((field) => {
              const stored = offsets[field.key];
              const unreadable = stored === undefined;
              const current =
                unreadable ? null : stored / field.perUnit;
              return (
                <div
                  key={field.key}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    flexWrap: "wrap",
                  }}
                >
                  <span style={{ ...body, minWidth: isMobile ? "auto" : "12em" }}>
                    {field.label}
                  </span>
                  <span style={{ ...mono, minWidth: "6em", color: "var(--color-text)" }}>
                    {unreadable
                      ? "unreadable"
                      : `${current! > 0 ? "+" : ""}${current!.toFixed(
                          field.perUnit === 10 ? 1 : 0,
                        )} ${field.unit}`}
                  </span>
                  <input
                    type="number"
                    step={field.step}
                    placeholder="new"
                    aria-label={`${field.label} offset`}
                    value={drafts[field.key] ?? ""}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [field.key]: e.target.value }))
                    }
                    style={input}
                  />
                  <button
                    type="button"
                    onClick={() => void apply(field)}
                    disabled={
                      busy !== null ||
                      drafts[field.key] === undefined ||
                      drafts[field.key].trim() === ""
                    }
                    style={button(
                      "primary",
                      busy !== null ||
                        drafts[field.key] === undefined ||
                        drafts[field.key].trim() === "",
                    )}
                  >
                    {busy === field.key ? "Applying…" : "Apply"}
                  </button>
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => void clearAll()}
              disabled={busy !== null}
              style={button("secondary", busy !== null)}
            >
              {busy === "__clear__" ? "Clearing…" : "Clear All Offsets"}
            </button>
            <button
              type="button"
              onClick={() => {
                setOutcome(null);
                void load();
              }}
              disabled={busy !== null}
              style={button("secondary", busy !== null)}
            >
              Refresh
            </button>
          </div>

          {outcome && (
            <p
              style={{
                ...body,
                marginTop: "12px",
                color:
                  outcome.kind === "ok"
                    ? "var(--color-success)"
                    : "var(--color-danger)",
              }}
            >
              {outcome.text}
            </p>
          )}
        </>
      )}
    </div>
  );
}

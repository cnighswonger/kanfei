/**
 * The console's yearly-rain-reset month (RAIN_YEAR_START).
 *
 * Vantage stores a single byte at EEPROM 0x2C, 1..12, that decides when
 * the yearly rain accumulator drops back to zero.  Default is January;
 * hydrological "water year" installs (US west coast, agricultural) want
 * July so a mid-winter storm season is not split across two yearly
 * totals.  Legacy stations reset every January without exposing a knob.
 *
 * Read-then-write.  Not much UI: a select and a before/after echo
 * for confidence.  Commit routes through Settings' top-level SaveBar
 * via the ``registerSatellite`` handshake — Design v32 P2 asked us
 * to drop the panel's own Save button so users have one commit
 * surface for the whole page.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ApiError,
  fetchRainSeason,
  setRainSeason,
} from "../../api/client.ts";

type LoadStatus = "loading" | "loaded" | "error" | "unsupported";

const card: React.CSSProperties = {
  background: "transparent",
  borderRadius: 0,
  border: "0.8px solid var(--color-border)",
  padding: "18px 20px",
  marginBottom: "16px",
};

const title: React.CSSProperties = {
  margin: "0 0 16px 0",
  fontSize: "calc(16px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  color: "var(--color-text)",
};

const body: React.CSSProperties = {
  fontSize: "calc(13px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  lineHeight: 1.5,
};

const button: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg)",
  color: "var(--color-text)",
  fontFamily: "var(--font-body)",
  fontSize: "calc(13px * var(--font-scale))",
  cursor: "pointer",
};

const select: React.CSSProperties = {
  ...button,
  cursor: "pointer",
  minWidth: "9em",
};

// Full month names.  Console has room for the full word on its LCD; the
// UI has more.
const MONTHS: Array<{ value: number; label: string }> = [
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];

function monthLabel(n: number | null | undefined): string {
  if (n == null) return "—";
  return MONTHS.find((m) => m.value === n)?.label ?? String(n);
}

type SatelliteEntry = {
  dirty: boolean;
  label: string;
  save: () => Promise<void>;
  revert: () => void;
};

interface Props {
  supported: boolean;
  isMobile: boolean;
  /**
   * Optional hook into the parent Settings' SaveBar.  Registered on
   * mount, updated on dirty-state change, unregistered on unmount.
   * Absent for standalone use in tests or Storybook.
   */
  registerSatellite?: (key: string, entry: SatelliteEntry | null) => void;
}

export default function RainSeason({ supported, isMobile, registerSatellite }: Props) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [current, setCurrent] = useState<number | null>(null);
  const [draft, setDraft] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applyResult, setApplyResult] = useState<{
    before: number | null;
    after: number | null;
  } | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await fetchRainSeason();
      setCurrent(result.month);
      setDraft(result.month);
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

  // Blank rather than an explicit "not supported" card, matching the
  // sibling console panels.  #249 is about a user hunting for an action
  // and finding nothing; this panel offers no action on legacy stations,
  // and a permanent apology row would be noise.
  if (status === "unsupported") return null;

  const dirty = draft != null && draft !== current;

  // Keep the apply function up-to-date without triggering a re-register
  // on every keystroke of unrelated state — the parent SaveBar calls
  // whichever version is current when the user clicks.
  const applyRef = useRef<() => Promise<void>>(async () => {});
  applyRef.current = async () => {
    if (draft == null) return;
    setSaving(true);
    setError(null);
    try {
      const result = await setRainSeason(draft);
      setApplyResult({ before: result.before, after: result.after });
      if (result.after != null) {
        setCurrent(result.after);
        setDraft(result.after);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const draftLabelForBar = dirty ? `rain season → ${monthLabel(draft)}` : "";

  useEffect(() => {
    if (!registerSatellite) return;
    registerSatellite("rain_year_start", {
      dirty,
      label: draftLabelForBar,
      save: () => applyRef.current(),
      revert: () => {
        setDraft(current);
        setError(null);
      },
    });
    return () => registerSatellite("rain_year_start", null);
  }, [registerSatellite, dirty, draftLabelForBar, current]);

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={title}>Rain Season Start</h3>

      <p style={{ ...body, marginTop: 0 }}>
        Month the console's yearly rain total resets to zero. Default is
        January. A hydrological water year setting (July for most of the
        US West Coast) keeps a winter storm season inside a single yearly
        total instead of splitting it across two.
      </p>

      {status === "loading" && <p style={body}>Reading the console…</p>}
      {status === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read rain-season month: {error}
        </p>
      )}

      {status === "loaded" && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "16px",
            flexWrap: "wrap",
          }}
        >
          <label style={body}>
            Reset month
            <select
              style={{ ...select, marginLeft: "10px" }}
              value={draft ?? ""}
              onChange={(e) => setDraft(parseInt(e.target.value, 10))}
              disabled={saving}
            >
              {MONTHS.map((m) => (
                <option key={m.value} value={m.value}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          {applyResult && !dirty && (
            <span style={{ ...body, opacity: 0.75 }}>
              {applyResult.before === applyResult.after
                ? `Console reads: ${monthLabel(applyResult.after)}`
                : `${monthLabel(applyResult.before)} → ${monthLabel(applyResult.after)}`}
            </span>
          )}
        </div>
      )}

      {error && status === "loaded" && (
        <p style={{ ...body, color: "var(--color-danger)", marginBottom: 0 }}>
          Save failed: {error}
        </p>
      )}
    </div>
  );
}

/**
 * Operations that destroy data on the console.
 *
 * Both are legitimate — a user replacing a console mid-season needs to
 * restore the yearly rain total, and one reclaiming archive memory needs
 * CLRLOG. Neither is dangerous because it is destructive; they are
 * dangerous because a plain button would make them look routine.
 *
 * So each is preceded by a preflight read that states the cost in the
 * user's own numbers, and the confirmation names what will be lost. The
 * design call (#264) was to show the price before it is paid rather than
 * offer an undo afterwards: a confirmation that names the loss is a
 * decision, an undo offered later is a consolation.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  clearConsoleArchive,
  fetchArchivePreflight,
  fetchRainPreflight,
  setYearlyRain,
} from "../../api/client.ts";
import type { ArchivePreflight, RainPreflight } from "../../api/types.ts";

type LoadStatus = "loading" | "loaded" | "error" | "unsupported";

const card: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  marginBottom: "16px",
};

const title: React.CSSProperties = {
  margin: "0 0 8px 0",
  fontSize: "calc(18px * var(--font-scale))",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const subTitle: React.CSSProperties = {
  ...title,
  fontSize: "calc(15px * var(--font-scale))",
  margin: "0 0 6px 0",
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
  color: "var(--color-text)",
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
  width: "8em",
  boxSizing: "border-box",
};

function dangerButton(disabled: boolean): React.CSSProperties {
  return {
    fontFamily: "var(--font-body)",
    fontSize: "calc(13px * var(--font-scale))",
    padding: "7px 14px",
    borderRadius: "6px",
    border: "1px solid var(--color-danger)",
    background: "transparent",
    color: "var(--color-danger)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.5 : 1,
  };
}

function ageMinutes(iso: string | null): number | null {
  if (!iso) return null;
  return (Date.now() - new Date(iso).getTime()) / 60_000;
}

function formatAge(minutes: number): string {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.floor(minutes)} min ago`;
  const h = Math.floor(minutes / 60);
  if (h < 24) return `${h}h ${Math.floor(minutes % 60)}m ago`;
  return `${Math.floor(h / 24)}d ${h % 24}h ago`;
}

interface Props {
  supported: boolean;
  isMobile: boolean;
}

export default function ConsoleDataOperations({ supported, isMobile }: Props) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [rain, setRain] = useState<RainPreflight | null>(null);
  const [archive, setArchive] = useState<ArchivePreflight | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<{ kind: "ok" | "fail"; text: string } | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const [r, a] = await Promise.all([
        fetchRainPreflight(),
        fetchArchivePreflight().catch(() => null),
      ]);
      setRain(r);
      setArchive(a);
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

  async function applyRain() {
    if (!rain || draft.trim() === "") return;
    const value = Number(draft);
    if (!Number.isFinite(value) || value < 0) {
      setOutcome({ kind: "fail", text: "Enter a total of 0 mm or more." });
      return;
    }

    const age = ageMinutes(rain.last_stored_at);
    const lines = [
      `Overwrite the console's yearly rain total?`,
      ``,
      `Console now holds: ${rain.console_mm ?? "unknown"} mm`,
      `Will be set to:    ${value} mm`,
    ];
    if (rain.difference_mm != null && Math.abs(rain.difference_mm) >= 0.1) {
      lines.push(
        ``,
        `The console has counted ${rain.difference_mm.toFixed(1)} mm that ` +
          `Kanfei has not recorded${age != null ? ` (last reading ${formatAge(age)})` : ""}.` +
          ` That rainfall is what you are discarding.`,
      );
    }
    lines.push(``, `This cannot be undone on the console.`);

    if (!window.confirm(lines.join("\n"))) return;

    setBusy("rain");
    setOutcome(null);
    try {
      const result = await setYearlyRain(value);
      setOutcome({
        kind: "ok",
        text: `Yearly rain set to ${result.after_mm ?? value} mm (was ${
          result.before_mm ?? "unknown"
        } mm).`,
      });
      setDraft("");
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await load();
      setOutcome({ kind: "fail", text: message });
    } finally {
      setBusy(null);
    }
  }

  async function clearArchive() {
    const held = archive?.records_in_kanfei;
    const confirmText = [
      `Clear the console's archive memory?`,
      ``,
      held != null
        ? `Kanfei has already downloaded ${held.toLocaleString()} records — ` +
          `those are safe and stay in your history.`
        : `Kanfei's record count could not be read, so it is not certain ` +
          `how much has already been downloaded.`,
      ``,
      `Anything the console holds that Kanfei has NOT yet downloaded will ` +
        `be destroyed. Force an archive sync first if you are unsure.`,
      ``,
      `This cannot be undone on the console.`,
    ].join("\n");

    if (!window.confirm(confirmText)) return;

    setBusy("archive");
    setOutcome(null);
    try {
      await clearConsoleArchive();
      setOutcome({ kind: "ok", text: "Console archive memory cleared." });
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      await load();
      setOutcome({ kind: "fail", text: message });
    } finally {
      setBusy(null);
    }
  }

  const age = rain ? ageMinutes(rain.last_stored_at) : null;
  const stale = age != null && age > 30;

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={title}>Console Data</h3>
      <p style={{ ...body, marginTop: 0 }}>
        These change data held on the console itself and cannot be undone
        there.
      </p>

      {status === "loading" && <p style={body}>Reading the console…</p>}
      {status === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read console state: {error}
        </p>
      )}

      {status === "loaded" && (
        <>
          {/* --- Yearly rain --- */}
          <div style={{ marginTop: "14px" }}>
            <h4 style={subTitle}>Yearly rain total</h4>
            <p style={body}>
              Console: <span style={mono}>{rain?.console_mm ?? "—"} mm</span>
              {rain?.last_stored_mm != null && (
                <>
                  {" · "}Kanfei last recorded{" "}
                  <span style={mono}>{rain.last_stored_mm} mm</span>
                  {age != null && ` (${formatAge(age)})`}
                </>
              )}
            </p>

            {rain?.difference_mm != null && Math.abs(rain.difference_mm) >= 0.1 && (
              <p style={{ ...body, color: stale ? "var(--color-warning)" : undefined }}>
                The console has counted{" "}
                <strong style={{ color: "var(--color-text)" }}>
                  {rain.difference_mm.toFixed(1)} mm
                </strong>{" "}
                that Kanfei has not recorded. Overwriting the total discards
                that rainfall.
              </p>
            )}

            {rain && !rain.collector_known && (
              <p style={{ ...body, color: "var(--color-danger)" }}>
                The rain collector type is unknown, so the console will not
                accept a new total — a click is 0.01in, 0.2 mm or 0.1 mm
                depending on the collector, and guessing would risk a
                twofold error.
              </p>
            )}

            <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap", marginTop: "8px" }}>
              <input
                type="number"
                step="0.1"
                min="0"
                placeholder="mm"
                aria-label="New yearly rain total"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                style={input}
                disabled={busy !== null || !rain?.collector_known}
              />
              <button
                type="button"
                onClick={() => void applyRain()}
                disabled={busy !== null || draft.trim() === "" || !rain?.collector_known}
                style={dangerButton(
                  busy !== null || draft.trim() === "" || !rain?.collector_known,
                )}
              >
                {busy === "rain" ? "Setting…" : "Overwrite total"}
              </button>
              {rain?.last_stored_mm != null && (
                <button
                  type="button"
                  onClick={() => setDraft(String(rain.last_stored_mm))}
                  disabled={busy !== null || !rain.collector_known}
                  style={{
                    ...body,
                    background: "none",
                    border: "none",
                    padding: 0,
                    cursor: "pointer",
                    color: "var(--color-accent)",
                  }}
                >
                  use Kanfei's last reading
                </button>
              )}
            </div>
          </div>

          {/* --- Archive memory --- */}
          <div style={{ marginTop: "18px", paddingTop: "14px", borderTop: "1px solid var(--color-border)" }}>
            <h4 style={subTitle}>Console archive memory</h4>
            <p style={body}>
              Kanfei holds{" "}
              <span style={mono}>
                {archive?.records_in_kanfei?.toLocaleString() ?? "—"}
              </span>{" "}
              downloaded records. Those stay in your history; only records
              the console has not yet handed over are lost.
            </p>
            <button
              type="button"
              onClick={() => void clearArchive()}
              disabled={busy !== null}
              style={dangerButton(busy !== null)}
            >
              {busy === "archive" ? "Clearing…" : "Clear console archive"}
            </button>
          </div>

          <div style={{ marginTop: "14px" }}>
            <button
              type="button"
              onClick={() => {
                setOutcome(null);
                void load();
              }}
              disabled={busy !== null}
              style={{
                ...body,
                background: "none",
                border: "none",
                padding: 0,
                cursor: "pointer",
                color: "var(--color-accent)",
              }}
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

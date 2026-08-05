/**
 * Reconciles Kanfei's configured location with the console's own copy.
 *
 * A Vantage keeps latitude/longitude in EEPROM and uses them for its
 * sunrise/sunset calculation and pressure correction, so the two
 * disagreeing produces quietly wrong derived data rather than an obvious
 * failure. Nothing else in the UI surfaces the console's copy.
 *
 * The console stores signed tenths of a degree (~11 km per step), so it
 * can never hold Kanfei's value exactly. Everything here follows from
 * that: the comparison is made at the console's resolution, the push is
 * one-directional, and the result shows what the console rounded to
 * rather than what was sent.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  fetchConsoleLocation,
  setConsoleLocation,
} from "../../api/client.ts";
import type { ConsoleLocation as ConsoleLocationState } from "../../api/types.ts";

type LoadStatus = "loading" | "loaded" | "error" | "unsupported";

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

interface Props {
  supported: boolean;
  /** Kanfei's configured coordinates. */
  latitude: number;
  longitude: number;
}

/** True when the two agree as closely as the console's format allows.
 *
 * Compares the *distance* rather than re-deriving what the console should
 * hold. Replicating the rounding here is wrong in two ways at once:
 * Python's `round` is banker's rounding (35.85 and 35.75 both give 358
 * tenths) while JavaScript's `Math.round` goes half-up toward positive
 * infinity (35.85 -> 35.9, -78.75 -> -78.7). At a half-step coordinate the
 * comparator and the writer therefore disagree, and a console that was
 * just written correctly shows as permanently wrong. Found by Codex on
 * #265 R1.
 *
 * Any console value within half a step of Kanfei's is as close as the
 * format can get, whichever way the writer broke the tie.
 */
function agreesAtResolution(
  kanfei: number,
  console_: number,
  resolutionDeg: number,
): boolean {
  const step = resolutionDeg || 0.1;
  // Epsilon absorbs binary-float error in the stored value and in the
  // subtraction; it is orders of magnitude below a tenth of a degree.
  return Math.abs(kanfei - console_) <= step / 2 + 1e-9;
}

export default function ConsoleLocation({
  supported,
  latitude,
  longitude,
}: Props) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [loc, setLoc] = useState<ConsoleLocationState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pushing, setPushing] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      setLoc(await fetchConsoleLocation());
      setStatus("loaded");
    } catch (err) {
      // 501 means this station has no console-held location at all —
      // a normal state for legacy hardware, not a failure to report.
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

  async function push() {
    setPushing(true);
    setResult(null);
    try {
      const r = await setConsoleLocation(latitude, longitude);
      setResult(
        r.after
          ? `Console now reads ${r.after.latitude}, ${r.after.longitude}.`
          : "Written, but the console could not be re-read to confirm.",
      );
      await load();
    } catch (err) {
      // Any failure may or may not have landed, so re-read rather than
      // asserting the console is unchanged (#252).
      const message = err instanceof Error ? err.message : String(err);
      await load();
      setResult(`Failed: ${message}`);
    } finally {
      setPushing(false);
    }
  }

  const agrees =
    loc != null &&
    agreesAtResolution(latitude, loc.latitude, loc.resolution_deg) &&
    agreesAtResolution(longitude, loc.longitude, loc.resolution_deg);

  return (
    <div style={{ marginTop: "12px", paddingTop: "12px", borderTop: "1px solid var(--color-border)" }}>
      {status === "loading" && <p style={body}>Reading the console's location…</p>}

      {status === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read the console's location: {error}
        </p>
      )}

      {status === "loaded" && loc && (
        <>
          <p style={body}>
            Console holds{" "}
            <span style={mono}>
              {loc.latitude}, {loc.longitude}
            </span>{" "}
            {agrees ? (
              <span style={{ color: "var(--color-success)" }}>
                — matches your location as closely as it can store it.
              </span>
            ) : (
              <span style={{ color: "var(--color-warning)" }}>
                — does not match your location. The console uses this for
                its own sunrise, sunset and pressure correction.
              </span>
            )}
          </p>
          {!agrees && (
            <button
              type="button"
              onClick={() => void push()}
              disabled={pushing}
              style={{
                fontFamily: "var(--font-body)",
                fontSize: "calc(13px * var(--font-scale))",
                padding: "7px 14px",
                borderRadius: "6px",
                border: "1px solid var(--color-border)",
                background: "var(--color-bg-secondary)",
                color: "var(--color-text)",
                cursor: pushing ? "not-allowed" : "pointer",
                opacity: pushing ? 0.5 : 1,
              }}
            >
              {pushing ? "Writing…" : "Send my location to the console"}
            </button>
          )}
          {/* Stated up front rather than as a surprise in the result: the
              console cannot hold what Kanfei holds. */}
          <p style={{ ...body, marginTop: "6px", opacity: 0.8 }}>
            The console stores to the nearest {loc.resolution_deg}° (about
            11 km), so it will round your coordinates. Kanfei keeps the
            precise values.
          </p>
          {result && (
            <p style={{ ...body, marginTop: "6px" }}>{result}</p>
          )}
        </>
      )}
    </div>
  );
}

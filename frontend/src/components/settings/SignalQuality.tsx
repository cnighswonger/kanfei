/**
 * How well the console is hearing its transmitters.
 *
 * This is the diagnostic for #230: a transmitter drops out, its dashed
 * sentinel is stored as a real reading, and the poisoned daily maximum is
 * published for the rest of the day. The symptom appears hours after the
 * cause. These counters name the cause while it is happening.
 *
 * Read-only, and manual-refresh only. Each read takes the serial lock
 * briefly, and on a single-master port that is enough to stall a poll —
 * a panel refreshing on a timer while left open would starve the logger.
 */

import { useCallback, useEffect, useState } from "react";
import { ApiError, fetchSignalQuality } from "../../api/client.ts";
import type { SignalQuality as SignalQualityData } from "../../api/types.ts";

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

const mono: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "calc(12px * var(--font-scale))",
};

const th: React.CSSProperties = {
  ...body,
  textAlign: "left",
  padding: "4px 14px 4px 0",
  fontWeight: 400,
  opacity: 0.75,
};

const td: React.CSSProperties = {
  ...mono,
  padding: "4px 14px 4px 0",
  color: "var(--color-text)",
  whiteSpace: "nowrap",
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

/** Reception rate as a percentage, or null when nothing has been heard yet.
 *
 * Denominator is received + missed: `resync` and `crc_errors` describe how
 * the received packets fared, so counting them here would double-count.
 */
function receptionRate(d: SignalQualityData): number | null {
  const attempted = d.packets_received + d.missed;
  return attempted === 0 ? null : (d.packets_received / attempted) * 100;
}

interface Props {
  supported: boolean;
  isMobile: boolean;
}

export default function SignalQuality({ supported, isMobile }: Props) {
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [data, setData] = useState<SignalQualityData | null>(null);
  const [readAt, setReadAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await fetchSignalQuality();
      setData(result);
      setReadAt(new Date());
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

  // Blank rather than an explicit "not supported" card, matching
  // ConsoleHighsLows: #249 is about a user hunting for an action and
  // finding nothing, and this panel offers no action. The 501 branch is
  // reachable only as a race — `supported.signal_quality` is computed by
  // the same predicate that gates the handler.
  if (status === "unsupported") return null;

  const rate = data ? receptionRate(data) : null;

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h3 style={title}>Signal Quality</h3>

      <p style={{ ...body, marginTop: 0 }}>
        How well the console is hearing its transmitters. Every figure is a
        total since station midnight, not a rate — take two readings apart
        to see how reception is going right now.
      </p>

      {status === "loading" && <p style={body}>Reading the console…</p>}
      {status === "error" && (
        <p style={{ ...body, color: "var(--color-danger)" }}>
          Could not read reception diagnostics: {error}
        </p>
      )}

      {status === "loaded" && data && (
        <>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: "22em" }}>
              <tbody>
                <tr>
                  <th style={th}>Packets received</th>
                  <td style={td}>{data.packets_received.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>Missed</th>
                  <td style={td}>{data.missed.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>Reception rate</th>
                  <td style={td}>
                    {rate == null ? "—" : `${rate.toFixed(2)} %`}
                  </td>
                </tr>
                <tr>
                  <th style={th}>Longest unbroken run</th>
                  <td style={td}>
                    {data.max_consecutive_received.toLocaleString()}
                  </td>
                </tr>
                <tr>
                  <th style={th}>Resyncs</th>
                  <td style={td}>{data.resync.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>CRC errors</th>
                  <td style={td}>{data.crc_errors.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>Transmitters heard</th>
                  <td style={td}>
                    {data.receivers == null
                      ? "not reported"
                      : data.receivers.length === 0
                        ? "none listed"
                        : data.receivers.join(", ")}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p style={{ ...body, marginTop: "12px", marginBottom: 0 }}>
            A long unbroken run is good — it counts packets received in a
            row, not packets lost. Resyncs and CRC errors climbing while the
            reception rate falls point at interference or a weak
            transmitter; a rate near zero with nothing heard points at a
            transmitter that has stopped.
          </p>

          {data.receivers != null && data.receivers.length === 0 && (
            <p style={{ ...body, marginBottom: 0 }}>
              The console listed no transmitter IDs. A Vue answers this way
              normally — read the counters above, not this row, to tell
              whether it is hearing anything.
            </p>
          )}

          <div
            style={{
              marginTop: "16px",
              display: "flex",
              alignItems: "center",
              gap: "12px",
              flexWrap: "wrap",
            }}
          >
            <button type="button" style={button} onClick={() => void load()}>
              Refresh
            </button>
            {readAt && (
              <span style={{ ...body, opacity: 0.75 }}>
                Read at {readAt.toLocaleTimeString()}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}

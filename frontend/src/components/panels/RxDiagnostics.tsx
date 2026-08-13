/**
 * Reception diagnostics for consoles that report them.
 *
 * Two orthogonal reads bundled behind one refresh:
 *   - RXCHECK counters (how well the console is hearing its transmitters)
 *   - OPMODE radio state (which band/channel it's listening on, plus the
 *     per-unit crystal calibration and console temp)
 *
 * The tile hides itself entirely when neither read is available — the
 * driver doesn't support RXCHECK, or the caller isn't an admin. A partial
 * result (counters yes, OPMODE no, or vice versa) shows only the section
 * that answered.
 *
 * Manual-refresh only. Each read takes the console's serial lock briefly
 * and a polling tile would starve the logger on a single-master port.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, fetchRadioState, fetchSignalQuality } from "../../api/client.ts";
import type { RadioState, SignalQuality } from "../../api/types.ts";

type LoadStatus = "loading" | "loaded" | "error" | "unsupported";

const MUTED = "#abb4ca";

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  marginBottom: "16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 12px 0",
  fontSize: "calc(18px * var(--font-scale))",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const subTitle: React.CSSProperties = {
  margin: "16px 0 8px 0",
  fontSize: "calc(13px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  color: MUTED,
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const bodyText: React.CSSProperties = {
  color: "var(--color-text-secondary)",
  fontSize: "calc(13px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  lineHeight: 1.5,
  margin: 0,
};

const th: React.CSSProperties = {
  ...bodyText,
  textAlign: "left",
  padding: "4px 14px 4px 0",
  fontWeight: 400,
  opacity: 0.75,
};

const td: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "calc(12px * var(--font-scale))",
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

function receptionRate(d: SignalQuality): number | null {
  const attempted = d.packets_received + d.missed;
  return attempted === 0 ? null : (d.packets_received / attempted) * 100;
}

interface Props {
  isMobile: boolean;
}

export default function RxDiagnostics({ isMobile }: Props) {
  const [rxStatus, setRxStatus] = useState<LoadStatus>("loading");
  const [rx, setRx] = useState<SignalQuality | null>(null);
  const [rxError, setRxError] = useState<string | null>(null);

  const [radioStatus, setRadioStatus] = useState<LoadStatus>("loading");
  const [radio, setRadio] = useState<RadioState | null>(null);

  const [readAt, setReadAt] = useState<Date | null>(null);
  const [hidden, setHidden] = useState(false);

  // Reads hold the console serial lock and can wait up to 20s. If the
  // user navigates away mid-fetch, we must not touch state after the
  // component unmounts. Tracked as a ref rather than a boolean state so
  // the check itself doesn't trigger a re-render.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setRxStatus("loading");
    setRadioStatus("loading");
    setRxError(null);

    const rxPromise = fetchSignalQuality().then(
      (result) => ({ ok: true, result }) as const,
      (err) => ({ ok: false, err }) as const,
    );
    const radioPromise = fetchRadioState().then(
      (result) => ({ ok: true, result }) as const,
      (err) => ({ ok: false, err }) as const,
    );
    const [rxRes, radioRes] = await Promise.all([rxPromise, radioPromise]);

    if (!mountedRef.current) return;

    // Hide the whole tile when the driver doesn't do RXCHECK, when the
    // user is not authenticated as admin, or when the daemon isn't up.
    // Any of these mean this page has nothing to show — better to omit
    // it than to render a persistent error card on About.
    if (!rxRes.ok) {
      const err = rxRes.err;
      if (err instanceof ApiError && (err.status === 401 || err.status === 403 || err.status === 501)) {
        setHidden(true);
        return;
      }
    }

    if (rxRes.ok) {
      setRx(rxRes.result);
      setRxStatus("loaded");
    } else {
      setRxError(rxRes.err instanceof Error ? rxRes.err.message : String(rxRes.err));
      setRxStatus("error");
    }

    if (radioRes.ok) {
      setRadio(radioRes.result);
      setRadioStatus("loaded");
    } else if (radioRes.err instanceof ApiError && radioRes.err.status === 501) {
      setRadioStatus("unsupported");
    } else {
      setRadioStatus("error");
    }

    setReadAt(new Date());
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (hidden) return null;

  const rate = rx ? receptionRate(rx) : null;

  return (
    <div style={{ ...cardStyle, padding: isMobile ? "14px" : "20px" }}>
      <h3 style={sectionTitle}>RX Diagnostics</h3>

      <p style={{ ...bodyText, marginBottom: "8px" }}>
        Console reception and radio state. Read once per refresh — the
        counters reset at station midnight, so two readings apart show
        the current rate.
      </p>

      {(rxStatus === "loading" || radioStatus === "loading") && (
        <p style={bodyText}>Reading the console…</p>
      )}

      {rxStatus === "error" && (
        <p style={{ ...bodyText, color: "var(--color-danger)" }}>
          Could not read reception counters: {rxError}
        </p>
      )}

      {rxStatus === "loaded" && rx && (
        <>
          <div style={subTitle}>Reception</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: "20em" }}>
              <tbody>
                <tr>
                  <th style={th}>Packets received</th>
                  <td style={td}>{rx.packets_received.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>Missed</th>
                  <td style={td}>{rx.missed.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>Reception rate</th>
                  <td style={td}>{rate == null ? "—" : `${rate.toFixed(2)} %`}</td>
                </tr>
                <tr>
                  <th style={th}>Longest unbroken run</th>
                  <td style={td}>{rx.max_consecutive_received.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>Resyncs</th>
                  <td style={td}>{rx.resync.toLocaleString()}</td>
                </tr>
                <tr>
                  <th style={th}>CRC errors</th>
                  <td style={td}>{rx.crc_errors.toLocaleString()}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {radioStatus === "loaded" && radio && (
        <>
          <div style={subTitle}>Radio</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: "20em" }}>
              <tbody>
                {radio.DOM !== undefined && (
                  <tr>
                    <th style={th}>Domain</th>
                    <td style={td}>{radio.DOM}</td>
                  </tr>
                )}
                {radio.BAND !== undefined && (
                  <tr>
                    <th style={th}>Band</th>
                    <td style={td}>{radio.BAND}</td>
                  </tr>
                )}
                {radio.CHAN !== undefined && (
                  <tr>
                    <th style={th}>Channel</th>
                    <td style={td}>{radio.CHAN}</td>
                  </tr>
                )}
                {radio.XTLCAL !== undefined && (
                  <tr>
                    <th style={th}>Crystal cal</th>
                    <td style={td}>{radio.XTLCAL}</td>
                  </tr>
                )}
                {radio.TEMP !== undefined && (
                  <tr>
                    <th style={th}>Console temp (raw)</th>
                    <td style={td}>{radio.TEMP}</td>
                  </tr>
                )}
                {radio.TEMP_CAL !== undefined && (
                  <tr>
                    <th style={th}>Console temp cal</th>
                    <td style={td}>{radio.TEMP_CAL}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
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
          <span style={{ ...bodyText, opacity: 0.75 }}>
            Read at {readAt.toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  );
}

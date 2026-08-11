/**
 * Multi-station aggregate view for barometer calibration (#298).
 *
 * Shows the algorithm result from `/api/station/barometer-reference`'s
 * `aggregate` field: console-side median, per-station medians, the two
 * gates (min-stations, cross-station spread), and a recommended offset
 * when both gates pass.  When a gate fails, the diagnostic explains
 * which one and shows the per-station values.
 *
 * Distinct from the sibling "pick a single METAR" section below it in
 * `BarometerCalibration.tsx`: the aggregate is the primary path (the
 * one that will not silently commit to a wrong value); the single-
 * reference selector remains as a manual override for operators who
 * have a specific reason to pick one station.
 */

import type {
  BarometerAggregate,
  BarometerSkipReason,
} from "../../api/types.ts";

const card: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  marginBottom: "16px",
};

const title: React.CSSProperties = {
  margin: "0 0 12px 0",
  fontSize: "calc(16px * var(--font-scale))",
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

const badge = (kind: "pass" | "hold"): React.CSSProperties => ({
  display: "inline-block",
  padding: "2px 8px",
  borderRadius: "999px",
  fontSize: "calc(11px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  fontWeight: 600,
  background:
    kind === "pass"
      ? "color-mix(in oklab, var(--color-success) 25%, transparent)"
      : "color-mix(in oklab, var(--color-warning) 25%, transparent)",
  color:
    kind === "pass" ? "var(--color-success)" : "var(--color-warning)",
});

// Human-readable one-liner per skip reason.  Kept as a lookup so the
// wire codes stay greppable and the UI copy is in one place.
const SKIP_LABEL: Record<BarometerSkipReason, string> = {
  no_console_samples:
    "No console barometer readings in the last window — is the poller running?",
  insufficient_console_samples:
    "Too few console samples in the last window to trust the median.",
  no_metar_available:
    "No METAR observations returned in the last 2 hours.",
  insufficient_stations:
    "Only one METAR station voted — need at least two to cross-check.",
  cross_station_disagreement:
    "Stations disagree beyond tolerance — HOLDING existing offset.",
};

interface Props {
  aggregate: BarometerAggregate | null;
  isMobile: boolean;
  /** Called with the recommended offset in thousandths inHg when the
   *  operator clicks Apply.  Parent decides how to route it — usually
   *  it pre-fills the manual calibration input so the operator sees
   *  what will be sent. */
  onApplyRecommendation?: (offsetThousandthsInhg: number) => void;
}

export default function BaroCalibrationAggregate({
  aggregate,
  isMobile,
  onApplyRecommendation,
}: Props) {
  if (aggregate == null) return null;

  const { console: c, per_station_medians, cross_station_spread_hpa,
          recommendation, thresholds } = aggregate;

  const stationsPass =
    aggregate.n_stations_considered >= thresholds.min_stations;
  const spreadPass =
    cross_station_spread_hpa != null &&
    cross_station_spread_hpa <= thresholds.cross_station_spread_threshold_hpa;
  const consolePass =
    c != null && c.n_samples >= thresholds.min_console_samples;

  return (
    <div style={{ ...card, padding: isMobile ? "12px" : "20px" }}>
      <h4 style={title}>Multi-Station Aggregate</h4>

      <p style={{ ...body, marginTop: 0 }}>
        Compares the median of your console's last {thresholds.console_window_minutes} min
        of barometer readings against the median-of-medians of nearby METAR
        stations. Both gates must pass to recommend a write — one
        anomalous METAR alone cannot pin the console to a wrong offset.
      </p>

      {/* Gate summary */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap",
                    marginBottom: "12px" }}>
        <span style={badge(consolePass ? "pass" : "hold")}>
          Console: {c?.n_samples ?? 0} samples
          {c != null && ` · ${c.median_hpa.toFixed(2)} hPa`}
        </span>
        <span style={badge(stationsPass ? "pass" : "hold")}>
          Stations: {aggregate.n_stations_considered} / {thresholds.min_stations} min
        </span>
        <span style={badge(spreadPass ? "pass" : "hold")}>
          Spread:{" "}
          {cross_station_spread_hpa == null
            ? "—"
            : `${cross_station_spread_hpa.toFixed(2)} hPa`}
          {" / "}
          {thresholds.cross_station_spread_threshold_hpa.toFixed(1)} hPa max
        </span>
      </div>

      {/* Per-station table */}
      {per_station_medians.length > 0 && (
        <div style={{ overflowX: "auto", marginBottom: "12px" }}>
          <table style={{ borderCollapse: "collapse", minWidth: "26em" }}>
            <thead>
              <tr>
                <th style={th}>Station</th>
                <th style={th}>Distance</th>
                <th style={th}>Median inHg</th>
                <th style={th}>Obs</th>
                <th style={th}>Obs spread</th>
              </tr>
            </thead>
            <tbody>
              {per_station_medians.map((s) => (
                <tr key={s.station_id}>
                  <td style={td}>
                    {s.station_id}
                    <span style={{ ...body, opacity: 0.7, marginLeft: "6px" }}>
                      {s.station_name}
                    </span>
                  </td>
                  <td style={td}>{s.distance_miles.toFixed(1)} mi {s.bearing_cardinal}</td>
                  <td style={td}>{s.median_altimeter_inhg.toFixed(3)}</td>
                  <td style={td}>{s.n_obs}</td>
                  <td style={td}>
                    {(s.obs_spread_thousandths_inhg / 1000).toFixed(3)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Verdict + apply */}
      {recommendation.should_apply ? (
        <div>
          <p style={{ ...body, marginTop: 0, color: "var(--color-success)" }}>
            {aggregate.n_stations_considered} stations agree within{" "}
            {cross_station_spread_hpa?.toFixed(2)} hPa. Recommended offset:{" "}
            <strong>
              {(recommendation.offset_inhg ?? 0) >= 0 ? "+" : ""}
              {recommendation.offset_inhg?.toFixed(3)} inHg
            </strong>
            {" ("}
            {(recommendation.offset_thousandths_inhg ?? 0) >= 0 ? "+" : ""}
            {recommendation.offset_thousandths_inhg}
            {" thousandths)"}
          </p>
          {onApplyRecommendation &&
            recommendation.offset_thousandths_inhg != null && (
              <button
                type="button"
                style={button}
                onClick={() =>
                  onApplyRecommendation(
                    recommendation.offset_thousandths_inhg as number,
                  )
                }
              >
                Use recommended offset
              </button>
            )}
        </div>
      ) : (
        <p style={{ ...body, marginTop: 0, color: "var(--color-warning)" }}>
          {recommendation.skip_reason
            ? SKIP_LABEL[recommendation.skip_reason]
            : "Aggregate not ready."}
        </p>
      )}
    </div>
  );
}

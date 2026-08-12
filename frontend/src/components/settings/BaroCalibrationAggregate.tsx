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
import { hpaToInHg, inHgToHpa } from "../../utils/units.ts";

/** The operator's chosen pressure unit — station config's
 *  ``pressure_unit`` field, threaded down from `Settings.tsx`.  All
 *  pressure values in this panel format to this unit so the operator
 *  never has to read `1016.7 hPa` next to `30.020 inHg` in the same
 *  card.  Defaults to `inHg` upstream to match the code default in
 *  `utils/units.ts`. */
type PressureUnit = "inHg" | "hPa";

function fmtPressureFromHpa(hpa: number, unit: PressureUnit): string {
  return unit === "hPa"
    ? `${hpa.toFixed(2)} hPa`
    : `${hpaToInHg(hpa).toFixed(3)} inHg`;
}

function fmtOffsetFromInHg(inHg: number, unit: PressureUnit): string {
  const v = unit === "hPa" ? inHgToHpa(inHg) : inHg;
  const decimals = unit === "hPa" ? 2 : 3;
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(decimals)} ${unit}`;
}

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
  unsettled_console:
    "Your console's pressure is moving faster than a calibration " +
    "would remain valid for — try again in a calmer window.",
  unsettled_regional:
    "Nearby METAR stations report rapid pressure change across the " +
    "region — the weather is dynamic right now; try again in 60–90 min.",
};

interface Props {
  aggregate: BarometerAggregate | null;
  isMobile: boolean;
  /** Operator's chosen pressure unit — every pressure in the panel
   *  formats to this.  Threaded from Settings.tsx via
   *  `BarometerCalibration`. */
  pressureUnit: PressureUnit;
  /** Called with the ABSOLUTE median-of-medians target in thousandths
   *  inHg (i.e. what the console should be told to display), NOT the
   *  signed offset delta.  BAR= on the wire takes an absolute pressure;
   *  passing the delta would require the parent to know the current
   *  console reading, which it does but the aggregate has already done
   *  that math when it produced the recommendation. */
  onApplyRecommendation?: (targetThousandthsInhg: number) => void;
}

export default function BaroCalibrationAggregate({
  aggregate,
  isMobile,
  pressureUnit,
  onApplyRecommendation,
}: Props) {
  if (aggregate == null) return null;

  const { console: c, per_station_medians, cross_station_spread_hpa,
          recommendation, thresholds } = aggregate;

  // Both gates count SURVIVORS after MAD outlier rejection.  A drifted
  // AWOS at a rural airfield cannot inflate the raw count past the
  // min-stations gate, and its 3 hPa reading cannot poison the spread
  // gate — but it still rides in `per_station_medians` (with
  // `is_outlier: true`) so the panel can show WHY the count dropped.
  const n_excluded =
    aggregate.n_stations_considered - aggregate.n_stations_used;
  const stationsPass =
    aggregate.n_stations_used >= thresholds.min_stations;
  const spreadPass =
    cross_station_spread_hpa != null &&
    cross_station_spread_hpa <= thresholds.cross_station_spread_threshold_hpa;
  // Both the sample-count gate AND the quiescence σ-gate must pass
  // for the console badge to read green — otherwise the badge would
  // stay green under `unsettled_console` and contradict the
  // diagnostic below it (Codex R1 nit on #310).
  const consolePass =
    c != null &&
    c.n_samples >= thresholds.min_console_samples &&
    c.stdev_hpa <= thresholds.console_stdev_threshold_hpa;

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
          {c != null && ` · ${fmtPressureFromHpa(c.median_hpa, pressureUnit)}`}
        </span>
        <span style={badge(stationsPass ? "pass" : "hold")}>
          Stations: {aggregate.n_stations_used}
          {n_excluded > 0 &&
            ` of ${aggregate.n_stations_considered} (${n_excluded} excluded)`}
          {" / "}
          {thresholds.min_stations} min
        </span>
        <span style={badge(spreadPass ? "pass" : "hold")}>
          Spread:{" "}
          {cross_station_spread_hpa == null
            ? "—"
            : fmtPressureFromHpa(cross_station_spread_hpa, pressureUnit)}
          {" / "}
          {fmtPressureFromHpa(
            thresholds.cross_station_spread_threshold_hpa,
            pressureUnit,
          )} max
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
                <th style={th}>Median {pressureUnit}</th>
                <th style={th}>Obs</th>
                <th style={th}>Obs spread</th>
              </tr>
            </thead>
            <tbody>
              {per_station_medians.map((s) => {
                // Excluded stations still ride in the response so the
                // operator can see WHY a station dropped out — hiding
                // them would surprise a user whose count "silently" fell
                // from N to M.  Strike them out and grey them.
                const rowStyle = s.is_outlier
                  ? { textDecoration: "line-through" as const, opacity: 0.55 }
                  : undefined;
                return (
                  <tr key={s.station_id} style={rowStyle}>
                    <td style={td}>
                      {s.station_id}
                      <span style={{ ...body, opacity: 0.7, marginLeft: "6px" }}>
                        {s.station_name}
                      </span>
                      {s.is_outlier && (
                        <span style={{
                          ...body,
                          marginLeft: "6px",
                          fontStyle: "italic",
                          color: "var(--color-warning)",
                        }}>
                          outlier
                        </span>
                      )}
                    </td>
                    <td style={td}>{s.distance_miles.toFixed(1)} mi {s.bearing_cardinal}</td>
                    <td style={td}>
                      {pressureUnit === "hPa"
                        ? inHgToHpa(s.median_altimeter_inhg).toFixed(2)
                        : s.median_altimeter_inhg.toFixed(3)}
                    </td>
                    <td style={td}>{s.n_obs}</td>
                    <td style={td}>
                      {pressureUnit === "hPa"
                        ? inHgToHpa(s.obs_spread_thousandths_inhg / 1000).toFixed(2)
                        : (s.obs_spread_thousandths_inhg / 1000).toFixed(3)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Verdict + apply */}
      {recommendation.should_apply ? (
        <div>
          <p style={{ ...body, marginTop: 0, color: "var(--color-success)" }}>
            {aggregate.n_stations_used} stations agree within{" "}
            {cross_station_spread_hpa == null
              ? "—"
              : fmtPressureFromHpa(cross_station_spread_hpa, pressureUnit)}
            . Recommended offset:{" "}
            <strong>
              {fmtOffsetFromInHg(recommendation.offset_inhg ?? 0, pressureUnit)}
            </strong>
          </p>
          {onApplyRecommendation &&
            recommendation.median_of_medians_thousandths_inhg != null && (
              <button
                type="button"
                style={button}
                onClick={() =>
                  onApplyRecommendation(
                    recommendation.median_of_medians_thousandths_inhg as number,
                  )
                }
              >
                Use recommended offset
              </button>
            )}
        </div>
      ) : (
        <div>
          <p style={{ ...body, marginTop: 0, color: "var(--color-warning)" }}>
            {recommendation.skip_reason
              ? SKIP_LABEL[recommendation.skip_reason]
              : "Aggregate not ready."}
          </p>
          {/* Operator override on HOLD.  Rendered ONLY when the
              backend says hold_override_allowed — which is only the
              cross-station-disagreement skip.  Writes the SAME
              weighted-median value the algorithm computed; the
              multi-station cross-check still governs the write VALUE,
              only the write DECISION is delegated to the operator.
              Distinct visual treatment (secondary style + explicit
              warning copy) so it does not read as the primary action.
              See #307 for the design discussion.  */}
          {onApplyRecommendation &&
            recommendation.hold_override_allowed &&
            recommendation.median_of_medians_thousandths_inhg != null && (
              <div style={{ marginTop: "8px" }}>
                <p style={{ ...body, marginTop: 0, marginBottom: "8px" }}>
                  The algorithm cannot autonomously commit to a write
                  here, but the weighted-median recommendation is{" "}
                  <strong>
                    {fmtOffsetFromInHg(
                      recommendation.offset_inhg ?? 0,
                      pressureUnit,
                    )}
                  </strong>
                  {". If you have out-of-band knowledge that this is right for your location, you can commit to it anyway."}
                </p>
                <button
                  type="button"
                  style={{
                    ...button,
                    background: "var(--color-bg-secondary)",
                    border: "1px solid var(--color-border)",
                    color: "var(--color-text)",
                  }}
                  onClick={() =>
                    onApplyRecommendation(
                      recommendation.median_of_medians_thousandths_inhg as number,
                    )
                  }
                >
                  Accept anyway (override HOLD)
                </button>
              </div>
            )}
        </div>
      )}
    </div>
  );
}

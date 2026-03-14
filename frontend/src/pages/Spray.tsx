/**
 * Spray Advisor page — helps farmers determine optimal spray windows
 * based on product constraints and weather forecast data.
 */
import { useState, useEffect, useCallback } from "react";
import { useWeatherData } from "../context/WeatherDataContext.tsx";
import { useIsMobile } from "../hooks/useIsMobile.ts";
import {
  fetchSprayProducts,
  createSprayProduct,
  updateSprayProduct,
  deleteSprayProduct,
  resetSprayPresets,
  fetchSpraySchedules,
  createSpraySchedule,
  deleteSpraySchedule,
  updateSprayScheduleStatus,
  evaluateSpraySchedule,
  quickCheckSpray,
  fetchSprayConditions,
  createSprayOutcome,
  fetchProductStats,
} from "../api/client.ts";
import type {
  SprayProduct,
  SpraySchedule,
  SprayEvaluation,
  SprayConditions,
  SprayProductStats,
  ConstraintCheck,
} from "../api/types.ts";

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 12px 0",
  fontSize: "16px",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const btnStyle: React.CSSProperties = {
  padding: "6px 14px",
  borderRadius: 6,
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  cursor: "pointer",
  fontSize: 13,
  fontFamily: "var(--font-body)",
};

const accentBtn: React.CSSProperties = {
  ...btnStyle,
  background: "var(--color-accent)",
  color: "#fff",
  border: "none",
  fontWeight: 600,
};

const inputStyle: React.CSSProperties = {
  padding: "6px 10px",
  borderRadius: 6,
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  fontFamily: "var(--font-body)",
  fontSize: 13,
};

const labelStyle: React.CSSProperties = {
  fontSize: 12,
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: 4,
  display: "block",
};

function confidenceColor(c: string): string {
  const upper = (c ?? "").toUpperCase();
  if (upper.startsWith("HIGH")) return "var(--color-success)";
  if (upper.startsWith("MEDIUM")) return "var(--color-warning, #f59e0b)";
  if (upper.startsWith("LOW")) return "var(--color-danger)";
  return "var(--color-text-muted)";
}

// ---------------------------------------------------------------------------
// Conditions strip
// ---------------------------------------------------------------------------

function ConditionsStrip({ conditions }: { conditions: SprayConditions | null }) {
  if (!conditions) return null;

  const items: { label: string; value: string; ok: boolean }[] = [];

  if (conditions.wind_speed_mph != null || conditions.wind_gust_mph != null) {
    const worst = Math.max(conditions.wind_speed_mph ?? 0, conditions.wind_gust_mph ?? 0);
    const parts: string[] = [];
    if (conditions.wind_speed_mph != null) parts.push(`${conditions.wind_speed_mph} mph`);
    if (conditions.wind_gust_mph != null) parts.push(`gust ${conditions.wind_gust_mph.toFixed(0)}`);
    items.push({
      label: "Wind",
      value: parts.join(", "),
      ok: worst <= 10,
    });
  }
  if (conditions.temperature_f != null) {
    items.push({
      label: "Temp",
      value: `${conditions.temperature_f.toFixed(0)}\u00B0F`,
      ok: conditions.temperature_f >= 40 && conditions.temperature_f <= 90,
    });
  }
  if (conditions.humidity_pct != null) {
    items.push({
      label: "Humidity",
      value: `${conditions.humidity_pct}%`,
      ok: true,
    });
  }
  if (conditions.rain_rate != null) {
    items.push({
      label: "Rain",
      value: conditions.rain_rate > 0 ? `${conditions.rain_rate.toFixed(2)} in/hr` : "None",
      ok: conditions.rain_rate === 0,
    });
  }
  if (conditions.rain_daily != null) {
    items.push({
      label: "Daily Rain",
      value: `${conditions.rain_daily.toFixed(2)} in`,
      ok: conditions.rain_daily === 0,
    });
  }
  items.push({
    label: "Next Rain",
    value:
      conditions.next_rain_hours != null
        ? `~${conditions.next_rain_hours}h`
        : "None in 48h",
    ok: conditions.next_rain_hours == null || conditions.next_rain_hours > 2,
  });

  return (
    <div
      style={{
        ...cardStyle,
        display: "flex",
        flexWrap: "wrap",
        gap: 16,
        alignItems: "center",
        padding: "14px 20px",
        borderLeft: `4px solid ${conditions.overall_spray_ok ? "var(--color-success)" : "var(--color-danger)"}`,
      }}
    >
      <span
        style={{
          fontSize: 13,
          fontFamily: "var(--font-body)",
          fontWeight: 600,
          color: conditions.overall_spray_ok
            ? "var(--color-success)"
            : "var(--color-danger)",
          marginRight: 8,
        }}
      >
        {conditions.overall_spray_ok ? "Spray OK" : "Not Ideal"}
      </span>
      {items.map((item) => (
        <span
          key={item.label}
          style={{
            fontSize: 13,
            fontFamily: "var(--font-mono)",
            color: item.ok ? "var(--color-text)" : "var(--color-danger)",
          }}
        >
          <span style={{ color: "var(--color-text-secondary)", marginRight: 4 }}>
            {item.label}:
          </span>
          {item.value}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Constraint row
// ---------------------------------------------------------------------------

function ConstraintRow({ check }: { check: ConstraintCheck }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 0",
        fontSize: 13,
        fontFamily: "var(--font-body)",
      }}
    >
      <span style={{ fontSize: 14 }}>{check.passed ? "\u2705" : "\u274C"}</span>
      <span
        style={{
          fontWeight: 600,
          textTransform: "capitalize",
          minWidth: 80,
          color: "var(--color-text)",
        }}
      >
        {check.name.replace("_", " ")}
      </span>
      <span style={{ color: "var(--color-text-secondary)" }}>
        {check.current_value}
      </span>
      <span style={{ color: "var(--color-text-muted)" }}>
        (limit: {check.threshold})
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Go/No-Go badge
// ---------------------------------------------------------------------------

function GoNoGoBadge({ go, confidence }: { go: boolean; confidence?: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 700,
        fontFamily: "var(--font-body)",
        background: go
          ? "rgba(34, 197, 94, 0.15)"
          : "rgba(239, 68, 68, 0.15)",
        color: go ? "var(--color-success)" : "var(--color-danger)",
      }}
    >
      {go ? "GO" : "NO-GO"}
      {confidence && (
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: confidenceColor(confidence),
            flexShrink: 0,
          }}
        />
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Schedule card
// ---------------------------------------------------------------------------

function ScheduleCard({
  schedule,
  onReEvaluate,
  onComplete,
  onCancel,
  onDelete,
  onReactivate,
  onLogOutcome,
}: {
  schedule: SpraySchedule;
  onReEvaluate: () => void;
  onComplete: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onReactivate?: () => void;
  onLogOutcome?: (data: Parameters<typeof createSprayOutcome>[1]) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showOutcomeForm, setShowOutcomeForm] = useState(false);
  const ev = schedule.evaluation;
  const isPast = schedule.status === "completed" || schedule.status === "cancelled";

  return (
    <div
      style={{
        ...cardStyle,
        opacity: isPast ? 0.6 : 1,
        borderLeft: ev
          ? `4px solid ${ev.go ? "var(--color-success)" : "var(--color-danger)"}`
          : "4px solid var(--color-border)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 10,
        }}
      >
        <strong
          style={{
            fontSize: 14,
            fontFamily: "var(--font-body)",
            color: "var(--color-text)",
          }}
        >
          {schedule.product_name}
        </strong>
        <span
          style={{
            fontSize: 13,
            fontFamily: "var(--font-mono)",
            color: "var(--color-text-secondary)",
          }}
        >
          {schedule.planned_date} {schedule.planned_start}{'\u2013'}{schedule.planned_end}
        </span>
        {ev && <GoNoGoBadge go={schedule.status === "go"} confidence={ev.confidence} />}
        {isPast && (
          <span
            style={{
              fontSize: 11,
              fontFamily: "var(--font-body)",
              color: "var(--color-text-muted)",
              textTransform: "uppercase",
            }}
          >
            {schedule.status}
          </span>
        )}
        <span style={{ flex: 1 }} />
        {ev && (
          <button
            style={{ ...btnStyle, padding: "3px 8px", fontSize: 12 }}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? "Hide Details" : "Details"}
          </button>
        )}
      </div>

      {ev && (
        <p
          style={{
            margin: "8px 0 0",
            fontSize: 13,
            fontFamily: "var(--font-body)",
            color: "var(--color-text-secondary)",
            lineHeight: 1.5,
          }}
        >
          {ev.overall_detail}
        </p>
      )}

      {ev && ev.optimal_window && !ev.go && (
        <div
          style={{
            marginTop: 8,
            padding: "6px 10px",
            background: "var(--color-bg-secondary)",
            borderRadius: 6,
            fontSize: 12,
            fontFamily: "var(--font-mono)",
            color: "var(--color-accent)",
          }}
        >
          Next window: {formatWindow(ev.optimal_window)}
        </div>
      )}

      {expanded && ev && (
        <div style={{ marginTop: 12, padding: "8px 0", borderTop: "1px solid var(--color-border)" }}>
          {ev.constraints.map((c, i) => (
            <ConstraintRow key={i} check={c} />
          ))}

          {schedule.ai_commentary != null && (() => {
            const ai = typeof schedule.ai_commentary === "string"
              ? (() => { try { return JSON.parse(schedule.ai_commentary as string); } catch { return null; } })()
              : schedule.ai_commentary;
            if (!ai || !ai.detail) return null;
            return (
              <div
                style={{
                  marginTop: 10,
                  padding: "8px 12px",
                  background: "var(--color-bg-secondary)",
                  borderRadius: 6,
                  borderLeft: "3px solid var(--color-accent)",
                  fontSize: 13,
                  fontFamily: "var(--font-body)",
                  color: "var(--color-text)",
                  lineHeight: 1.5,
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 11, color: "var(--color-accent)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                  AI Advisory
                </span>
                <p style={{ margin: "4px 0 0" }}>{ai.detail}</p>
              </div>
            );
          })()}
        </div>
      )}

      {!isPast && (
        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 12,
            flexWrap: "wrap",
          }}
        >
          <button style={btnStyle} onClick={onReEvaluate}>
            Re-evaluate
          </button>
          <button
            style={btnStyle}
            onClick={() => setShowOutcomeForm(true)}
          >
            Complete
          </button>
          <button
            style={btnStyle}
            onClick={() => {
              if (window.confirm("Cancel this scheduled spray?")) onCancel();
            }}
          >
            Cancel
          </button>
          <button
            style={{ ...btnStyle, color: "var(--color-danger)" }}
            onClick={() => {
              if (window.confirm("Delete this spray schedule? This cannot be undone.")) onDelete();
            }}
          >
            Delete
          </button>
        </div>
      )}

      {isPast && schedule.status === "cancelled" && onReactivate && (
        <div style={{ marginTop: 10 }}>
          <button style={btnStyle} onClick={onReactivate}>
            Reactivate
          </button>
        </div>
      )}

      {showOutcomeForm && onLogOutcome && (
        <OutcomeForm
          onSubmit={(data) => {
            onLogOutcome(data);
            setShowOutcomeForm(false);
          }}
          onCancel={() => {
            onComplete();
            setShowOutcomeForm(false);
          }}
        />
      )}
    </div>
  );
}

function formatWindow(w: { start: string; end: string; duration_hours?: number }): string {
  const fmt = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    } catch {
      return iso;
    }
  };
  const dur = w.duration_hours ? ` (${w.duration_hours}h)` : "";
  return `${fmt(w.start)} \u2013 ${fmt(w.end)}${dur}`;
}

// ---------------------------------------------------------------------------
// Outcome form (shown when completing a spray)
// ---------------------------------------------------------------------------

const EFFECTIVENESS_LABELS = ["", "Ineffective", "Poor", "Fair", "Good", "Excellent"];

function OutcomeForm({
  onSubmit,
  onCancel,
}: {
  onSubmit: (data: {
    effectiveness: number;
    actual_rain_hours?: number | null;
    actual_wind_mph?: number | null;
    actual_temp_f?: number | null;
    drift_observed?: boolean;
    product_efficacy?: string | null;
    notes?: string | null;
  }) => void;
  onCancel: () => void;
}) {
  const [effectiveness, setEffectiveness] = useState(3);
  const [rainHours, setRainHours] = useState("");
  const [wind, setWind] = useState("");
  const [temp, setTemp] = useState("");
  const [drift, setDrift] = useState(false);
  const [efficacy, setEfficacy] = useState("effective");
  const [notes, setNotes] = useState("");

  const handleSubmit = () => {
    onSubmit({
      effectiveness,
      actual_rain_hours: rainHours ? parseFloat(rainHours) : null,
      actual_wind_mph: wind ? parseFloat(wind) : null,
      actual_temp_f: temp ? parseFloat(temp) : null,
      drift_observed: drift,
      product_efficacy: efficacy,
      notes: notes || null,
    });
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 12,
    fontFamily: "var(--font-body)",
    color: "var(--color-text-secondary)",
    display: "block",
    marginBottom: 2,
  };
  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "4px 8px",
    fontSize: 13,
    fontFamily: "var(--font-mono)",
    background: "var(--color-bg-card)",
    color: "var(--color-text)",
    border: "1px solid var(--color-border)",
    borderRadius: 4,
    boxSizing: "border-box",
  };

  return (
    <div
      style={{
        background: "var(--color-bg-card)",
        borderRadius: 8,
        border: "1px solid var(--color-accent)",
        padding: 16,
        marginTop: 8,
      }}
    >
      <strong style={{ fontSize: 13, fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
        Log Outcome
      </strong>

      {/* Effectiveness slider */}
      <div style={{ marginTop: 10 }}>
        <label style={labelStyle}>
          Effectiveness: {effectiveness}/5 {'\u2014'} {EFFECTIVENESS_LABELS[effectiveness]}
        </label>
        <input
          type="range"
          min={1}
          max={5}
          value={effectiveness}
          onChange={(e) => setEffectiveness(parseInt(e.target.value))}
          style={{ width: "100%", accentColor: "var(--color-accent)" }}
        />
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 10,
            fontFamily: "var(--font-body)",
            color: "var(--color-text-muted)",
          }}
        >
          <span>Ineffective</span>
          <span>Excellent</span>
        </div>
      </div>

      {/* Structured fields */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 10,
          marginTop: 10,
        }}
      >
        <div>
          <label style={labelStyle}>Rain after (hrs)</label>
          <input
            type="number"
            step="0.5"
            placeholder="N/A"
            value={rainHours}
            onChange={(e) => setRainHours(e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>Wind (mph)</label>
          <input
            type="number"
            step="1"
            placeholder="N/A"
            value={wind}
            onChange={(e) => setWind(e.target.value)}
            style={inputStyle}
          />
        </div>
        <div>
          <label style={labelStyle}>Temp ({'\u00b0'}F)</label>
          <input
            type="number"
            step="1"
            placeholder="N/A"
            value={temp}
            onChange={(e) => setTemp(e.target.value)}
            style={inputStyle}
          />
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, marginTop: 10, alignItems: "center" }}>
        <label style={{ ...labelStyle, display: "flex", alignItems: "center", gap: 6, marginBottom: 0 }}>
          <input
            type="checkbox"
            checked={drift}
            onChange={(e) => setDrift(e.target.checked)}
            style={{ accentColor: "var(--color-accent)" }}
          />
          Drift observed
        </label>
        <div>
          <label style={labelStyle}>Efficacy</label>
          <select
            value={efficacy}
            onChange={(e) => setEfficacy(e.target.value)}
            style={{ ...inputStyle, width: "auto" }}
          >
            <option value="effective">Effective</option>
            <option value="partial">Partial</option>
            <option value="ineffective">Ineffective</option>
          </select>
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        <label style={labelStyle}>Notes</label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Observations during application..."
          style={{ ...inputStyle, minHeight: 50, resize: "vertical" }}
        />
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button style={accentBtn} onClick={handleSubmit}>
          Save Outcome
        </button>
        <button style={btnStyle} onClick={onCancel}>
          Skip
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Product stats badge
// ---------------------------------------------------------------------------

function ProductStatsBadge({ productId }: { productId: number }) {
  const [stats, setStats] = useState<SprayProductStats | null>(null);

  useEffect(() => {
    fetchProductStats(productId).then(setStats).catch(() => {});
  }, [productId]);

  if (!stats || stats.total_applications === 0) return null;

  return (
    <div
      style={{
        marginTop: 8,
        padding: "8px 12px",
        background: "var(--color-bg-card)",
        borderRadius: 6,
        fontSize: 12,
        fontFamily: "var(--font-mono)",
        color: "var(--color-text-secondary)",
      }}
    >
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
        <span>{stats.total_applications} applications</span>
        {stats.avg_effectiveness != null && (
          <span>Avg: {stats.avg_effectiveness}/5</span>
        )}
        {stats.success_rate != null && (
          <span
            style={{
              color: stats.success_rate >= 80 ? "var(--color-ok)" : stats.success_rate >= 50 ? "var(--color-warning)" : "var(--color-danger)",
            }}
          >
            {stats.success_rate}% success
          </span>
        )}
        {stats.drift_rate != null && stats.drift_rate > 0 && (
          <span style={{ color: "var(--color-warning)" }}>
            {stats.drift_rate}% drift
          </span>
        )}
      </div>
      {stats.tuned_thresholds.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 11, color: "var(--color-text-muted)" }}>
          {stats.tuned_thresholds.map((t) => (
            <div key={t.name}>{t.annotation}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Product card
// ---------------------------------------------------------------------------

function ProductCard({
  product,
  onEdit,
  onDelete,
}: {
  product: SprayProduct;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      style={{
        background: "var(--color-bg-secondary)",
        borderRadius: 8,
        border: "1px solid var(--color-border)",
        padding: "12px 16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <strong style={{ fontSize: 14, fontFamily: "var(--font-body)", color: "var(--color-text)" }}>
          {product.name}
        </strong>
        {product.is_preset && (
          <span
            style={{
              fontSize: 10,
              fontFamily: "var(--font-body)",
              color: "var(--color-text-muted)",
              textTransform: "uppercase",
              background: "var(--color-bg-card)",
              padding: "1px 6px",
              borderRadius: 4,
            }}
          >
            Preset
          </span>
        )}
        <span style={{ flex: 1 }} />
        <button style={{ ...btnStyle, padding: "2px 8px", fontSize: 11 }} onClick={onEdit}>
          Edit
        </button>
        <button
          style={{ ...btnStyle, padding: "2px 8px", fontSize: 11, color: "var(--color-danger)" }}
          onClick={onDelete}
        >
          Delete
        </button>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
          gap: "4px 16px",
          fontSize: 12,
          fontFamily: "var(--font-mono)",
          color: "var(--color-text-secondary)",
        }}
      >
        <span>Rain-free: {product.rain_free_hours}h</span>
        <span>Wind: &lt;{product.max_wind_mph} mph</span>
        <span>
          Temp: {product.min_temp_f}{'\u2013'}{product.max_temp_f}&deg;F
        </span>
        {(product.min_humidity_pct != null || product.max_humidity_pct != null) && (
          <span>
            Humidity: {product.min_humidity_pct ?? "any"}{'\u2013'}
            {product.max_humidity_pct ?? "any"}%
          </span>
        )}
      </div>
      {product.notes && (
        <p
          style={{
            margin: "6px 0 0",
            fontSize: 12,
            fontFamily: "var(--font-body)",
            color: "var(--color-text-muted)",
            fontStyle: "italic",
          }}
        >
          {product.notes}
        </p>
      )}
      <ProductStatsBadge productId={product.id} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Product form (add / edit)
// ---------------------------------------------------------------------------

function ProductForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: SprayProduct;
  onSave: (data: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [category, setCategory] = useState(initial?.category ?? "custom");
  const [rainFree, setRainFree] = useState(String(initial?.rain_free_hours ?? "2"));
  const [maxWind, setMaxWind] = useState(String(initial?.max_wind_mph ?? "10"));
  const [minTemp, setMinTemp] = useState(String(initial?.min_temp_f ?? "45"));
  const [maxTemp, setMaxTemp] = useState(String(initial?.max_temp_f ?? "85"));
  const [minHum, setMinHum] = useState(initial?.min_humidity_pct != null ? String(initial.min_humidity_pct) : "");
  const [maxHum, setMaxHum] = useState(initial?.max_humidity_pct != null ? String(initial.max_humidity_pct) : "");
  const [notes, setNotes] = useState(initial?.notes ?? "");

  const handleSubmit = () => {
    onSave({
      name,
      category,
      rain_free_hours: parseFloat(rainFree) || 2,
      max_wind_mph: parseFloat(maxWind) || 10,
      min_temp_f: parseFloat(minTemp) || 45,
      max_temp_f: parseFloat(maxTemp) || 85,
      min_humidity_pct: minHum ? parseFloat(minHum) : null,
      max_humidity_pct: maxHum ? parseFloat(maxHum) : null,
      notes: notes || null,
    });
  };

  const grid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "10px",
    marginBottom: 12,
  };

  return (
    <div style={{ ...cardStyle, border: "2px solid var(--color-accent)" }}>
      <h4 style={sectionTitle}>{initial ? "Edit Product" : "Add Custom Product"}</h4>
      <div style={grid}>
        <div>
          <label style={labelStyle}>Name</label>
          <input style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Category</label>
          <select style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="custom">Custom</option>
            <option value="herbicide_contact">Herbicide (Contact)</option>
            <option value="herbicide_systemic">Herbicide (Systemic)</option>
            <option value="fungicide_protectant">Fungicide (Protectant)</option>
            <option value="fungicide_systemic">Fungicide (Systemic)</option>
            <option value="insecticide_contact">Insecticide (Contact)</option>
            <option value="pgr">Plant Growth Regulator</option>
          </select>
        </div>
        <div>
          <label style={labelStyle}>Rain-free hours</label>
          <input type="number" step="0.5" style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={rainFree} onChange={(e) => setRainFree(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Max wind (mph)</label>
          <input type="number" style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={maxWind} onChange={(e) => setMaxWind(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Min temp (&deg;F)</label>
          <input type="number" style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={minTemp} onChange={(e) => setMinTemp(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Max temp (&deg;F)</label>
          <input type="number" style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={maxTemp} onChange={(e) => setMaxTemp(e.target.value)} />
        </div>
        <div>
          <label style={labelStyle}>Min humidity % (optional)</label>
          <input type="number" style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={minHum} onChange={(e) => setMinHum(e.target.value)} placeholder="any" />
        </div>
        <div>
          <label style={labelStyle}>Max humidity % (optional)</label>
          <input type="number" style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }} value={maxHum} onChange={(e) => setMaxHum(e.target.value)} placeholder="any" />
        </div>
      </div>
      <div>
        <label style={labelStyle}>Notes</label>
        <textarea
          style={{ ...inputStyle, width: "100%", boxSizing: "border-box", minHeight: 50, resize: "vertical" }}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button style={accentBtn} onClick={handleSubmit}>
          {initial ? "Save" : "Add Product"}
        </button>
        <button style={btnStyle} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Schedule form
// ---------------------------------------------------------------------------

function ScheduleForm({
  products,
  onSave,
  onCancel,
}: {
  products: SprayProduct[];
  onSave: (data: { product_id: number; planned_date: string; planned_start: string; planned_end: string; notes?: string }) => void;
  onCancel: () => void;
}) {
  const [productId, setProductId] = useState(products[0]?.id ?? 0);
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [start, setStart] = useState("08:00");
  const [end, setEnd] = useState("12:00");
  const [notes, setNotes] = useState("");

  return (
    <div style={{ ...cardStyle, border: "2px solid var(--color-accent)" }}>
      <h4 style={sectionTitle}>Schedule Spray</h4>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "10px",
          marginBottom: 12,
        }}
      >
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Product</label>
          <select
            style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
            value={productId}
            onChange={(e) => setProductId(Number(e.target.value))}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label style={labelStyle}>Date</label>
          <input
            type="date"
            style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>Start</label>
            <input
              type="time"
              style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>
          <div style={{ flex: 1 }}>
            <label style={labelStyle}>End</label>
            <input
              type="time"
              style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
        </div>
        <div style={{ gridColumn: "1 / -1" }}>
          <label style={labelStyle}>Notes (optional)</label>
          <input
            style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Field, target pest, etc."
          />
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          style={accentBtn}
          onClick={() =>
            onSave({
              product_id: productId,
              planned_date: date,
              planned_start: start,
              planned_end: end,
              notes: notes || undefined,
            })
          }
        >
          Schedule
        </button>
        <button style={btnStyle} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quick Check
// ---------------------------------------------------------------------------

function QuickCheck({ products }: { products: SprayProduct[] }) {
  const [productId, setProductId] = useState(products[0]?.id ?? 0);
  const [result, setResult] = useState<SprayEvaluation | null>(null);
  const [loading, setLoading] = useState(false);

  const handleCheck = () => {
    if (!productId) return;
    setLoading(true);
    setResult(null);
    quickCheckSpray(productId)
      .then(setResult)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  // Reset result when product changes.
  useEffect(() => {
    setResult(null);
  }, [productId]);

  return (
    <div style={cardStyle}>
      <h3 style={sectionTitle}>Quick Check</h3>
      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 200 }}>
          <label style={labelStyle}>Product</label>
          <select
            style={{ ...inputStyle, width: "100%", boxSizing: "border-box" }}
            value={productId}
            onChange={(e) => setProductId(Number(e.target.value))}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <button style={accentBtn} onClick={handleCheck} disabled={loading}>
          {loading ? "Checking\u2026" : "Check Now"}
        </button>
      </div>

      {result && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <GoNoGoBadge go={result.go} confidence={result.confidence} />
            <span
              style={{
                fontSize: 13,
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
              }}
            >
              {result.overall_detail}
            </span>
          </div>

          {result.constraints.map((c, i) => (
            <ConstraintRow key={i} check={c} />
          ))}

          {result.optimal_window && (
            <div
              style={{
                marginTop: 10,
                padding: "8px 12px",
                background: "var(--color-bg-secondary)",
                borderRadius: 6,
                fontSize: 13,
                fontFamily: "var(--font-mono)",
                color: "var(--color-accent)",
              }}
            >
              Best window: {formatWindow(result.optimal_window)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function Spray() {
  const { nowcast } = useWeatherData();
  const isMobile = useIsMobile();

  const [products, setProducts] = useState<SprayProduct[]>([]);
  const [schedules, setSchedules] = useState<SpraySchedule[]>([]);
  const [conditions, setConditions] = useState<SprayConditions | null>(null);
  const [loading, setLoading] = useState(true);

  // Forms.
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [showProductForm, setShowProductForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState<SprayProduct | null>(null);
  const [productsExpanded, setProductsExpanded] = useState(false);

  const loadData = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetchSprayProducts().catch(() => []),
      fetchSpraySchedules().catch(() => []),
      fetchSprayConditions().catch(() => null),
    ]).then(([p, s, c]) => {
      setProducts(p);
      setSchedules(s);
      setConditions(c);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    loadData();
    // Refresh conditions every 2 minutes.
    const timer = setInterval(() => {
      fetchSprayConditions().then(setConditions).catch(() => {});
    }, 120_000);
    return () => clearInterval(timer);
  }, [loadData]);

  // --- Handlers ---

  const handleCreateSchedule = async (data: {
    product_id: number;
    planned_date: string;
    planned_start: string;
    planned_end: string;
    notes?: string;
  }) => {
    try {
      const s = await createSpraySchedule(data);
      setSchedules((prev) => [s, ...prev]);
      setShowScheduleForm(false);
    } catch {
      /* TODO: error toast */
    }
  };

  const handleDeleteSchedule = async (id: number) => {
    try {
      await deleteSpraySchedule(id);
      setSchedules((prev) => prev.filter((s) => s.id !== id));
    } catch {
      /* ignore */
    }
  };

  const handleStatusChange = async (id: number, status: "completed" | "cancelled" | "pending") => {
    try {
      const updated = await updateSprayScheduleStatus(id, status);
      setSchedules((prev) => prev.map((s) => (s.id === id ? updated : s)));
    } catch {
      /* ignore */
    }
  };

  const handleLogOutcome = async (
    scheduleId: number,
    data: Parameters<typeof createSprayOutcome>[1],
  ) => {
    try {
      await createSprayOutcome(scheduleId, data);
      await handleStatusChange(scheduleId, "completed");
    } catch {
      /* ignore */
    }
  };

  const handleReEvaluate = async (id: number) => {
    try {
      const ev = await evaluateSpraySchedule(id);
      setSchedules((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, evaluation: ev, status: ev.go ? "go" : "no_go" }
            : s,
        ),
      );
    } catch {
      /* ignore */
    }
  };

  const handleSaveProduct = async (data: Record<string, unknown>) => {
    try {
      if (editingProduct) {
        const updated = await updateSprayProduct(editingProduct.id, data);
        setProducts((prev) =>
          prev.map((p) => (p.id === updated.id ? updated : p)),
        );
      } else {
        const created = await createSprayProduct(data as unknown as SprayProduct);
        setProducts((prev) => [...prev, created]);
      }
      setShowProductForm(false);
      setEditingProduct(null);
    } catch {
      /* ignore */
    }
  };

  const handleDeleteProduct = async (id: number) => {
    try {
      await deleteSprayProduct(id);
      setProducts((prev) => prev.filter((p) => p.id !== id));
      // Also remove related schedules from view.
      setSchedules((prev) => prev.filter((s) => s.product_id !== id));
    } catch {
      /* ignore */
    }
  };

  const handleResetPresets = async () => {
    try {
      const updated = await resetSprayPresets();
      setProducts(updated);
    } catch {
      /* ignore */
    }
  };

  // Separate upcoming vs past schedules.
  const upcoming = schedules.filter(
    (s) => s.status !== "completed" && s.status !== "cancelled",
  );
  const past = schedules.filter(
    (s) => s.status === "completed" || s.status === "cancelled",
  );

  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, padding: 20 }}>
        <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
          <h2
            style={{
              margin: "0 0 16px 0",
              fontSize: 24,
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            Spray Advisor
          </h2>
        </div>
        <p style={{ color: "var(--color-text-muted)", fontFamily: "var(--font-body)" }}>
          Loading...
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ flexShrink: 0, padding: "24px 24px 0" }}>
        <h2
          style={{
            margin: "0 0 16px 0",
            fontSize: 24,
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Spray Advisor
        </h2>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, padding: "0 24px 24px" }}>
      {/* Current conditions */}
      <ConditionsStrip conditions={conditions} />

      {/* AI spray advisory from nowcast */}
      {nowcast?.spray_advisory && (
        <div style={{ ...cardStyle, borderLeft: "4px solid var(--color-accent)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <span style={{ fontWeight: 600, fontSize: 11, color: "var(--color-accent)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              AI Spray Analysis
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 13, fontFamily: "var(--font-body)", color: "var(--color-text)", lineHeight: 1.5 }}>
            {nowcast.spray_advisory.summary}
          </p>
        </div>
      )}

      {/* Scheduled sprays */}
      <div style={{ marginTop: 8 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 12,
          }}
        >
          <h3 style={{ ...sectionTitle, margin: 0 }}>Scheduled Sprays</h3>
          <button
            style={accentBtn}
            onClick={() => setShowScheduleForm(!showScheduleForm)}
          >
            {showScheduleForm ? "Cancel" : "+ Schedule"}
          </button>
        </div>

        {showScheduleForm && (
          <ScheduleForm
            products={products}
            onSave={handleCreateSchedule}
            onCancel={() => setShowScheduleForm(false)}
          />
        )}

        {upcoming.length === 0 && !showScheduleForm && (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontFamily: "var(--font-body)",
              fontSize: 14,
            }}
          >
            No upcoming sprays scheduled.
          </p>
        )}

        {upcoming.map((s) => (
          <ScheduleCard
            key={s.id}
            schedule={s}
            onReEvaluate={() => handleReEvaluate(s.id)}
            onComplete={() => handleStatusChange(s.id, "completed")}
            onCancel={() => handleStatusChange(s.id, "cancelled")}
            onDelete={() => handleDeleteSchedule(s.id)}
            onLogOutcome={(data) => handleLogOutcome(s.id, data)}
          />
        ))}

        {past.length > 0 && (
          <details style={{ marginTop: 12 }}>
            <summary
              style={{
                cursor: "pointer",
                fontSize: 13,
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                marginBottom: 8,
              }}
            >
              Past sprays ({past.length})
            </summary>
            {past.map((s) => (
              <ScheduleCard
                key={s.id}
                schedule={s}
                onReEvaluate={() => handleReEvaluate(s.id)}
                onComplete={() => {}}
                onCancel={() => {}}
                onDelete={() => handleDeleteSchedule(s.id)}
                onReactivate={
                  s.status === "cancelled"
                    ? () => handleStatusChange(s.id, "pending")
                    : undefined
                }
              />
            ))}
          </details>
        )}
      </div>

      {/* Quick Check */}
      {products.length > 0 && <QuickCheck products={products} />}

      {/* Products section (collapsible) */}
      <div style={{ marginTop: 20 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            marginBottom: 12,
            cursor: "pointer",
          }}
          onClick={() => setProductsExpanded(!productsExpanded)}
        >
          <span style={{ fontSize: 14, color: "var(--color-text-muted)" }}>
            {productsExpanded ? "\u25BC" : "\u25B6"}
          </span>
          <h3 style={{ ...sectionTitle, margin: 0 }}>
            Products ({products.length})
          </h3>
        </div>

        {productsExpanded && (
          <>
            <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
              <button
                style={accentBtn}
                onClick={() => {
                  setEditingProduct(null);
                  setShowProductForm(true);
                }}
              >
                + Add Custom
              </button>
              <button style={btnStyle} onClick={handleResetPresets}>
                Reset Presets
              </button>
            </div>

            {(showProductForm || editingProduct) && (
              <ProductForm
                initial={editingProduct ?? undefined}
                onSave={handleSaveProduct}
                onCancel={() => {
                  setShowProductForm(false);
                  setEditingProduct(null);
                }}
              />
            )}

            <div
              style={{
                display: "grid",
                gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
                gap: 12,
              }}
            >
              {products.map((p) => (
                <ProductCard
                  key={p.id}
                  product={p}
                  onEdit={() => {
                    setEditingProduct(p);
                    setShowProductForm(true);
                  }}
                  onDelete={() => handleDeleteProduct(p.id)}
                />
              ))}
            </div>
          </>
        )}
      </div>
      </div>
    </div>
  );
}

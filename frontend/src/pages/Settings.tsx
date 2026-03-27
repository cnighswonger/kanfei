import { useState, useEffect, useCallback, useRef } from "react";
import { fetchConfig, updateConfig, fetchSerialPorts, reconnectStation, fetchWeatherLinkConfig, updateWeatherLinkConfig, clearRainDaily, clearRainYearly, forceArchive, fetchLocalUsage, fetchUsageStatus, fetchAnthropicCost, fetchDbStats, purgeTable, purgeAll, compactReadings, getDbBackupUrl, getDbExportUrl, fetchLogs, fetchNowcastPresets, triggerBackup, listBackups, deleteBackup, getBackupDownloadUrl } from "../api/client.ts";
import type { NowcastPresetOption } from "../api/client.ts";
import type { ConfigItem, WeatherLinkConfig, WeatherLinkCalibration, AlertThreshold, LocalUsageResponse, UsageStatus, DbStats, LogEntry } from "../api/types.ts";
import { useTheme } from "../context/ThemeContext.tsx";
import { useWeatherBackground } from "../context/WeatherBackgroundContext.tsx";
import { themes } from "../themes/index.ts";
import { ALL_SCENES, SCENE_LABELS, SCENE_GRADIENTS } from "../components/WeatherBackground.tsx";
import { API_BASE } from "../utils/constants.ts";
import { getTimezone, setTimezone as storeTimezone, resolveTimezone, getTimezoneOptions } from "../utils/timezone.ts";
import { useIsMobile } from "../hooks/useIsMobile.ts";
import { useFeatureFlags } from "../context/FeatureFlagsContext.tsx";
import StepLocation from "../components/setup/StepLocation.tsx";

// --- Shared styles ---

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 16px 0",
  fontSize: "18px",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

const labelStyle: React.CSSProperties = {
  fontSize: "13px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "6px",
  display: "block",
};

const inputStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const readOnlyInput: React.CSSProperties = {
  ...inputStyle,
  opacity: 0.6,
  cursor: "not-allowed",
};

const selectStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  cursor: "pointer",
  width: "100%",
  boxSizing: "border-box",
};

const fieldGroup: React.CSSProperties = {
  marginBottom: "16px",
};

const radioGroup: React.CSSProperties = {
  display: "flex",
  gap: "16px",
  flexWrap: "wrap",
};

const radioLabel: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text)",
  cursor: "pointer",
};

const checkboxLabel: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text)",
  cursor: "pointer",
};

const btnPrimary: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "10px 24px",
  borderRadius: "6px",
  border: "none",
  background: "var(--color-accent)",
  color: "#fff",
  cursor: "pointer",
  fontWeight: 600,
  transition: "background 0.15s",
};

function gridTwoCol(mobile?: boolean): React.CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: mobile ? "1fr" : "repeat(auto-fit, minmax(240px, 1fr))",
    gap: mobile ? "12px" : "16px",
  };
}

// --- Config key helpers ---

function getConfigValue(
  items: ConfigItem[],
  key: string,
): string | number | boolean {
  const item = items.find((i) => i.key === key);
  return item?.value ?? "";
}

function setConfigValue(
  items: ConfigItem[],
  key: string,
  value: string | number | boolean,
  label?: string,
  description?: string,
): ConfigItem[] {
  const idx = items.findIndex((i) => i.key === key);
  if (idx >= 0) {
    const updated = [...items];
    updated[idx] = { ...updated[idx], value };
    return updated;
  }
  return [...items, { key, value, label, description }];
}

// --- Usage Tab ---

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function UsageTab({
  config: _config,
  val,
  updateField,
  isMobile,
  cardStyle,
  sectionTitle,
  labelStyle,
  inputStyle,
  fieldGroup,
}: {
  config: ConfigItem[];
  val: (key: string) => string | number | boolean;
  updateField: (key: string, value: string | number | boolean) => void;
  isMobile: boolean;
  cardStyle: React.CSSProperties;
  sectionTitle: React.CSSProperties;
  labelStyle: React.CSSProperties;
  inputStyle: React.CSSProperties;
  fieldGroup: React.CSSProperties;
}) {
  const [localUsage, setLocalUsage] = useState<LocalUsageResponse | null>(null);
  const [usageStatus, setUsageStatus] = useState<UsageStatus | null>(null);
  const [costData, setCostData] = useState<Array<{ date: string; cost_usd: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [resuming, setResuming] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [local, status] = await Promise.all([
        fetchLocalUsage(),
        fetchUsageStatus(),
      ]);
      setLocalUsage(local);
      setUsageStatus(status);

      // If Anthropic Admin API is available, fetch cost data
      if (status.anthropic) {
        try {
          const costResp = await fetchAnthropicCost("30d");
          // Extract daily costs from Anthropic response
          const resp = costResp as { data?: Array<{ bucket_start_time: string; cost_cents: string }> };
          if (resp.data && Array.isArray(resp.data)) {
            const days: Array<{ date: string; cost_usd: number }> = resp.data.map(
              (d: { bucket_start_time: string; cost_cents: string }) => ({
                date: d.bucket_start_time?.substring(0, 10) ?? "",
                cost_usd: parseFloat(d.cost_cents ?? "0") / 100,
              }),
            );
            setCostData(days);
          }
        } catch {
          // Admin API may fail — not critical
        }
      }
    } catch {
      // Failed to load usage data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleResume = useCallback(async () => {
    setResuming(true);
    try {
      updateField("nowcast_enabled", true);
      updateField("usage_budget_paused", false);
    } finally {
      setResuming(false);
    }
  }, [updateField]);

  if (loading) {
    return (
      <div style={{ ...cardStyle, padding: "20px", textAlign: "center", color: "var(--color-text-muted)" }}>
        Loading usage data...
      </div>
    );
  }

  const today = localUsage?.today;
  const month = localUsage?.this_month;
  const allTime = localUsage?.all_time;
  const budget = usageStatus?.budget;
  const hasAnthropicApi = usageStatus?.anthropic ?? false;

  const statCardStyle: React.CSSProperties = {
    background: "var(--color-bg-secondary)",
    borderRadius: "var(--gauge-border-radius)",
    border: "1px solid var(--color-border)",
    padding: isMobile ? "12px" : "16px",
    flex: 1,
    minWidth: isMobile ? "100%" : "180px",
  };

  const statValueStyle: React.CSSProperties = {
    fontSize: "22px",
    fontWeight: 700,
    fontFamily: "var(--font-heading)",
    color: "var(--color-text)",
    marginBottom: "2px",
  };

  const statLabelStyle: React.CSSProperties = {
    fontSize: "11px",
    textTransform: "uppercase",
    letterSpacing: "0.5px",
    color: "var(--color-text-muted)",
    fontFamily: "var(--font-body)",
  };

  const budgetPct = budget && budget.limit_usd > 0
    ? Math.min(100, (budget.current_usd / budget.limit_usd) * 100)
    : 0;

  return (
    <>
      {/* Budget alert banner */}
      {budget?.paused && (
        <div style={{
          ...cardStyle,
          padding: "14px 20px",
          border: "2px solid var(--color-warning)",
          background: "var(--color-bg-card)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "10px",
        }}>
          <div>
            <strong style={{ color: "var(--color-warning)", fontFamily: "var(--font-body)", fontSize: "14px" }}>
              Nowcast Paused {'\u2014'} Budget Limit Reached
            </strong>
            <div style={{ fontSize: "13px", color: "var(--color-text-secondary)", fontFamily: "var(--font-body)", marginTop: "4px" }}>
              Monthly budget of ${budget.limit_usd.toFixed(2)} reached (${budget.current_usd.toFixed(2)} used).
              Nowcast generation has been automatically paused.
            </div>
          </div>
          <button
            onClick={handleResume}
            disabled={resuming}
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "13px",
              padding: "8px 16px",
              borderRadius: "6px",
              border: "1px solid var(--color-border)",
              background: "var(--color-accent)",
              color: "#fff",
              cursor: resuming ? "wait" : "pointer",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            Resume Nowcast
          </button>
        </div>
      )}

      {/* Summary cards */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Usage Summary</h3>
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          {/* Today */}
          <div style={statCardStyle}>
            <div style={statValueStyle}>${today?.estimated_cost_usd.toFixed(2) ?? "0.00"}</div>
            <div style={statLabelStyle}>Today</div>
            <div style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginTop: "4px" }}>
              {today?.calls ?? 0} calls {'\u00B7'} {formatTokens((today?.input_tokens ?? 0) + (today?.output_tokens ?? 0))} tokens
            </div>
          </div>

          {/* This Month */}
          <div style={statCardStyle}>
            <div style={statValueStyle}>${month?.estimated_cost_usd.toFixed(2) ?? "0.00"}</div>
            <div style={statLabelStyle}>This Month</div>
            <div style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginTop: "4px" }}>
              {month?.calls ?? 0} calls {'\u00B7'} {formatTokens((month?.input_tokens ?? 0) + (month?.output_tokens ?? 0))} tokens
            </div>
            {/* Budget progress bar */}
            {budget && budget.limit_usd > 0 && (
              <div style={{ marginTop: "8px" }}>
                <div style={{
                  height: "6px",
                  borderRadius: "3px",
                  background: "var(--color-border)",
                  overflow: "hidden",
                }}>
                  <div style={{
                    width: `${budgetPct}%`,
                    height: "100%",
                    borderRadius: "3px",
                    background: budgetPct >= 90 ? "var(--color-danger)" : budgetPct >= 70 ? "var(--color-warning)" : "var(--color-accent)",
                    transition: "width 0.3s ease",
                  }} />
                </div>
                <div style={{ fontSize: "11px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginTop: "3px" }}>
                  ${budget.current_usd.toFixed(2)} / ${budget.limit_usd.toFixed(2)} budget
                </div>
              </div>
            )}
          </div>

          {/* All Time */}
          <div style={statCardStyle}>
            <div style={statValueStyle}>${allTime?.estimated_cost_usd.toFixed(2) ?? "0.00"}</div>
            <div style={statLabelStyle}>All Time</div>
            <div style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginTop: "4px" }}>
              {allTime?.calls ?? 0} calls {'\u00B7'} {formatTokens((allTime?.input_tokens ?? 0) + (allTime?.output_tokens ?? 0))} tokens
            </div>
          </div>
        </div>
      </div>

      {/* Model Breakdown */}
      {localUsage?.model_breakdown && localUsage.model_breakdown.length > 0 && (
        <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
          <h3 style={sectionTitle}>Model Breakdown (This Month)</h3>
          <div style={{ overflowX: "auto" }}>
            <table style={{
              width: "100%",
              borderCollapse: "collapse",
              fontFamily: "var(--font-body)",
              fontSize: "13px",
            }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Model</th>
                  <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Calls</th>
                  <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Input</th>
                  <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Output</th>
                  <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Est. Cost</th>
                </tr>
              </thead>
              <tbody>
                {localUsage.model_breakdown.map((row) => (
                  <tr key={row.model} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td style={{ padding: "8px 12px", color: "var(--color-text)" }}>{row.model}</td>
                    <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>{row.calls}</td>
                    <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>{formatTokens(row.input_tokens)}</td>
                    <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>{formatTokens(row.output_tokens)}</td>
                    <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>${row.estimated_cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Daily Cost Trend (Anthropic Admin API) */}
      {hasAnthropicApi && costData.length > 0 && (
        <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
          <h3 style={sectionTitle}>Daily Cost (Last 30 Days)</h3>
          <div style={{ display: "flex", alignItems: "flex-end", gap: "2px", height: "80px" }}>
            {(() => {
              const maxCost = Math.max(...costData.map((d) => d.cost_usd), 0.01);
              return costData.map((day) => (
                <div
                  key={day.date}
                  title={`${day.date}: $${day.cost_usd.toFixed(2)}`}
                  style={{
                    flex: 1,
                    minWidth: "4px",
                    maxWidth: "20px",
                    height: `${Math.max(2, (day.cost_usd / maxCost) * 100)}%`,
                    background: "var(--color-accent)",
                    borderRadius: "2px 2px 0 0",
                    transition: "height 0.3s ease",
                  }}
                />
              ));
            })()}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px" }}>
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)" }}>
              {costData[0]?.date ?? ""}
            </span>
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)" }}>
              {costData[costData.length - 1]?.date ?? ""}
            </span>
          </div>
        </div>
      )}

      {/* Usage Settings */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Usage Settings</h3>

        <div style={fieldGroup}>
          <label style={labelStyle}>
            Anthropic Admin API Key
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
              Optional. Enables real-time cost data from your Anthropic account.
              Requires an Admin API key (sk-ant-admin...) from the Claude Console.
            </span>
          </label>
          <input
            type="password"
            style={inputStyle}
            value={String(val("anthropic_admin_api_key") || "")}
            onChange={(e) => updateField("anthropic_admin_api_key", e.target.value)}
            placeholder="sk-ant-admin..."
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: "16px", marginTop: "12px" }}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Monthly Budget (USD)</label>
            <input
              type="number"
              style={inputStyle}
              value={Number(val("usage_budget_monthly_usd")) || 0}
              onChange={(e) => updateField("usage_budget_monthly_usd", parseFloat(e.target.value) || 0)}
              min={0}
              step={1}
              placeholder="0 = unlimited"
            />
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", marginTop: "2px", display: "block" }}>
              Set to 0 for no limit
            </span>
          </div>

          <div style={{ ...fieldGroup, display: "flex", alignItems: "center", paddingTop: isMobile ? "0" : "18px" }}>
            <label style={{
              fontSize: "13px",
              fontFamily: "var(--font-body)",
              color: "var(--color-text-secondary)",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              cursor: "pointer",
            }}>
              <input
                type="checkbox"
                checked={val("usage_budget_auto_pause") === true}
                onChange={(e) => updateField("usage_budget_auto_pause", e.target.checked)}
              />
              Auto-pause nowcast when budget exceeded
            </label>
          </div>
        </div>
      </div>

      {/* Pricing Reference */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Model Pricing Reference</h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: "var(--font-body)",
            fontSize: "13px",
          }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Model</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Input / 1M</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Output / 1M</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Haiku 4.5", "$1.00", "$5.00"],
                ["Sonnet 4.5", "$3.00", "$15.00"],
                ["Opus 4.6", "$5.00", "$25.00"],
              ].map(([name, inp, out]) => (
                <tr key={name} style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <td style={{ padding: "8px 12px", color: "var(--color-text)" }}>{name}</td>
                  <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>{inp}</td>
                  <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>{out}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: "11px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginTop: "8px" }}>
          Local cost estimates are based on these rates. For actual billing, configure the Admin API key above.
        </div>
      </div>
    </>
  );
}

// --- Database Tab ---

const TABLE_LABELS: Record<string, string> = {
  sensor_readings: "Sensor Readings",
  archive_records: "Archive Records",
  nowcast_history: "Nowcast History",
  nowcast_verification: "Nowcast Verifications",
  nowcast_knowledge: "Knowledge Base",
  spray_schedules: "Spray Schedules",
  spray_outcomes: "Spray Outcomes",
  spray_products: "Spray Products",
  station_config: "Station Config",
};

const EXPORTABLE_TABLES = new Set([
  "sensor_readings", "archive_records", "nowcast_history",
  "nowcast_knowledge", "spray_schedules", "spray_outcomes",
]);

const PURGEABLE_TABLES = new Set([
  "sensor_readings", "archive_records", "nowcast_history",
  "nowcast_verification", "nowcast_knowledge", "spray_schedules", "spray_outcomes",
]);

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateShort(iso: string | null): string {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

function DatabaseTab({ isMobile }: { isMobile: boolean }) {
  const [stats, setStats] = useState<DbStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Purge dialog state
  const [purgeTarget, setPurgeTarget] = useState<string | null>(null);
  const [purgeMode, setPurgeMode] = useState<"date" | "full">("date");
  const [purgeBefore, setPurgeBefore] = useState("");
  const [purgeConfirm, setPurgeConfirm] = useState("");
  const [purgeLoading, setPurgeLoading] = useState(false);
  const [purgeResult, setPurgeResult] = useState<string | null>(null);

  // Purge-all dialog
  const [showPurgeAll, setShowPurgeAll] = useState(false);
  const [purgeAllConfirm, setPurgeAllConfirm] = useState("");
  const [purgeAllLoading, setPurgeAllLoading] = useState(false);

  // Compact dialog
  const [showCompact, setShowCompact] = useState(false);
  const [compactBefore, setCompactBefore] = useState("");
  const [compactConfirm, setCompactConfirm] = useState("");
  const [compactLoading, setCompactLoading] = useState(false);
  const [compactResult, setCompactResult] = useState<string | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const data = await fetchDbStats();
      setStats(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const totalRows = stats?.tables.reduce((s, t) => s + t.row_count, 0) ?? 0;

  const handlePurge = useCallback(async () => {
    if (!purgeTarget) return;
    setPurgeLoading(true);
    setPurgeResult(null);
    try {
      if (purgeMode === "date") {
        if (!purgeBefore) { setPurgeLoading(false); return; }
        const res = await purgeTable(purgeTarget, { before: purgeBefore });
        setPurgeResult(`Deleted ${res.deleted.toLocaleString()} records. ${res.remaining.toLocaleString()} remaining.`);
      } else {
        if (purgeConfirm !== "PURGE") { setPurgeLoading(false); return; }
        const res = await purgeTable(purgeTarget, { confirm: "PURGE" });
        setPurgeResult(`Deleted ${res.deleted.toLocaleString()} records. ${res.remaining.toLocaleString()} remaining.`);
      }
      loadStats();
    } catch (e) {
      setPurgeResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPurgeLoading(false);
    }
  }, [purgeTarget, purgeMode, purgeBefore, purgeConfirm, loadStats]);

  const handlePurgeAll = useCallback(async () => {
    if (purgeAllConfirm !== "DELETE DATABASE") return;
    setPurgeAllLoading(true);
    setPurgeResult(null);
    try {
      const res = await purgeAll("DELETE DATABASE");
      const total = Object.values(res).reduce((s, n) => s + n, 0);
      setPurgeResult(`Purged ${total.toLocaleString()} records across all tables.`);
      setShowPurgeAll(false);
      setPurgeAllConfirm("");
      loadStats();
    } catch (e) {
      setPurgeResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPurgeAllLoading(false);
    }
  }, [purgeAllConfirm, loadStats]);

  const handleCompact = useCallback(async () => {
    if (compactConfirm !== "COMPACT" || !compactBefore) return;
    setCompactLoading(true);
    setCompactResult(null);
    try {
      const res = await compactReadings(compactBefore, "COMPACT");
      setCompactResult(
        `Compacted ${res.original_rows.toLocaleString()} rows into ${res.compacted_rows.toLocaleString()} (removed ${res.deleted.toLocaleString()}).`
      );
      setShowCompact(false);
      setCompactConfirm("");
      setCompactBefore("");
      loadStats();
    } catch (e) {
      setCompactResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setCompactLoading(false);
    }
  }, [compactBefore, compactConfirm, loadStats]);

  if (loading) {
    return (
      <div style={{ ...cardStyle, padding: "20px", textAlign: "center", color: "var(--color-text-muted)" }}>
        Loading database stats...
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div style={{ ...cardStyle, padding: "20px", color: "var(--color-danger)" }}>
        Failed to load database stats: {error}
      </div>
    );
  }

  const sensorReadingsStats = stats?.tables.find(t => t.table === "sensor_readings");
  const sensorRowCount = sensorReadingsStats?.row_count ?? 0;
  const estimatedCompacted = Math.ceil(sensorRowCount / 30);

  return (
    <>
      {/* Status messages */}
      {purgeResult && (
        <div style={{
          ...cardStyle,
          padding: "12px 20px",
          border: purgeResult.startsWith("Error") ? "1px solid var(--color-danger)" : "1px solid var(--color-success)",
          color: purgeResult.startsWith("Error") ? "var(--color-danger)" : "var(--color-success)",
          fontSize: "14px",
          fontFamily: "var(--font-body)",
        }}>
          {purgeResult}
        </div>
      )}

      {compactResult && (
        <div style={{
          ...cardStyle,
          padding: "12px 20px",
          border: compactResult.startsWith("Error") ? "1px solid var(--color-danger)" : "1px solid var(--color-success)",
          color: compactResult.startsWith("Error") ? "var(--color-danger)" : "var(--color-success)",
          fontSize: "14px",
          fontFamily: "var(--font-body)",
        }}>
          {compactResult}
        </div>
      )}

      {/* Overview */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Database Overview</h3>
        <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginBottom: "2px" }}>
              File Size
            </div>
            <div style={{ fontSize: "20px", fontWeight: 700, fontFamily: "var(--font-heading)", color: "var(--color-text)" }}>
              {formatBytes(stats?.db_size_bytes ?? 0)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginBottom: "2px" }}>
              Total Rows
            </div>
            <div style={{ fontSize: "20px", fontWeight: 700, fontFamily: "var(--font-heading)", color: "var(--color-text)" }}>
              {totalRows.toLocaleString()}
            </div>
          </div>
        </div>
      </div>

      {/* Table Stats */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Tables</h3>
        <div style={{ overflowX: "auto" }}>
          <table style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: "var(--font-body)",
            fontSize: "13px",
          }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Table</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Rows</th>
                {!isMobile && (
                  <>
                    <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Oldest</th>
                    <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Newest</th>
                  </>
                )}
                <th style={{ textAlign: "right", padding: "8px 12px", color: "var(--color-text-muted)", fontWeight: 500 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {stats?.tables.map((t) => (
                <tr key={t.table} style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <td style={{ padding: "8px 12px", color: "var(--color-text)" }}>
                    {TABLE_LABELS[t.table] ?? t.table}
                  </td>
                  <td style={{ padding: "8px 12px", color: "var(--color-text)", textAlign: "right" }}>
                    {t.row_count.toLocaleString()}
                  </td>
                  {!isMobile && (
                    <>
                      <td style={{ padding: "8px 12px", color: "var(--color-text-muted)", textAlign: "right", fontSize: "12px" }}>
                        {formatDateShort(t.oldest)}
                      </td>
                      <td style={{ padding: "8px 12px", color: "var(--color-text-muted)", textAlign: "right", fontSize: "12px" }}>
                        {formatDateShort(t.newest)}
                      </td>
                    </>
                  )}
                  <td style={{ padding: "8px 12px", textAlign: "right" }}>
                    <div style={{ display: "flex", gap: "6px", justifyContent: "flex-end" }}>
                      {EXPORTABLE_TABLES.has(t.table) && (
                        <a
                          href={getDbExportUrl(t.table)}
                          download
                          style={{
                            fontSize: "11px",
                            padding: "3px 8px",
                            borderRadius: "4px",
                            border: "1px solid var(--color-border)",
                            background: "var(--color-bg-secondary)",
                            color: "var(--color-text-secondary)",
                            textDecoration: "none",
                            fontFamily: "var(--font-body)",
                          }}
                        >
                          Export
                        </a>
                      )}
                      {PURGEABLE_TABLES.has(t.table) && t.row_count > 0 && (
                        <button
                          onClick={() => {
                            setPurgeTarget(t.table);
                            setPurgeMode("date");
                            setPurgeBefore("");
                            setPurgeConfirm("");
                            setPurgeResult(null);
                          }}
                          style={{
                            fontSize: "11px",
                            padding: "3px 8px",
                            borderRadius: "4px",
                            border: "1px solid var(--color-border)",
                            background: "var(--color-bg-secondary)",
                            color: "var(--color-danger)",
                            cursor: "pointer",
                            fontFamily: "var(--font-body)",
                          }}
                        >
                          Purge
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Purge Dialog */}
      {purgeTarget && (
        <div style={{
          ...cardStyle,
          padding: isMobile ? "14px" : "20px",
          border: "2px solid var(--color-warning)",
        }}>
          <h3 style={{ ...sectionTitle, fontSize: "16px", marginBottom: "12px" }}>
            Purge: {TABLE_LABELS[purgeTarget] ?? purgeTarget}
          </h3>

          <div style={{ display: "flex", gap: "12px", marginBottom: "16px" }}>
            <label style={{ ...radioLabel, fontSize: "13px" }}>
              <input
                type="radio"
                checked={purgeMode === "date"}
                onChange={() => setPurgeMode("date")}
              />
              By date range
            </label>
            <label style={{ ...radioLabel, fontSize: "13px" }}>
              <input
                type="radio"
                checked={purgeMode === "full"}
                onChange={() => setPurgeMode("full")}
              />
              All records
            </label>
          </div>

          {purgeMode === "date" ? (
            <div style={fieldGroup}>
              <label style={labelStyle}>Delete records before:</label>
              <input
                type="date"
                style={{ ...inputStyle, maxWidth: "200px" }}
                value={purgeBefore}
                onChange={(e) => setPurgeBefore(e.target.value)}
              />
            </div>
          ) : (
            <div style={fieldGroup}>
              <div style={{
                fontSize: "13px",
                color: "var(--color-danger)",
                fontFamily: "var(--font-body)",
                marginBottom: "8px",
                fontWeight: 600,
              }}>
                This will permanently delete ALL records from {TABLE_LABELS[purgeTarget] ?? purgeTarget}.
              </div>
              <label style={labelStyle}>Type PURGE to confirm:</label>
              <input
                type="text"
                style={{ ...inputStyle, maxWidth: "200px" }}
                value={purgeConfirm}
                onChange={(e) => setPurgeConfirm(e.target.value)}
                placeholder="PURGE"
              />
            </div>
          )}

          <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
            <button
              style={{
                ...btnPrimary,
                background: "var(--color-danger)",
                opacity: purgeLoading || (purgeMode === "full" && purgeConfirm !== "PURGE") || (purgeMode === "date" && !purgeBefore) ? 0.5 : 1,
                cursor: purgeLoading ? "wait" : "pointer",
              }}
              onClick={handlePurge}
              disabled={purgeLoading || (purgeMode === "full" && purgeConfirm !== "PURGE") || (purgeMode === "date" && !purgeBefore)}
            >
              {purgeLoading ? "Deleting..." : "Delete Records"}
            </button>
            <button
              style={{ ...btnPrimary, background: "var(--color-bg-secondary)", color: "var(--color-text)", border: "1px solid var(--color-border)" }}
              onClick={() => setPurgeTarget(null)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Compact Card */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Compact Sensor Readings</h3>
        <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", fontFamily: "var(--font-body)", margin: "0 0 12px 0", lineHeight: "1.5" }}>
          Reduce storage by replacing raw sensor readings (every ~10s) with 5-minute averages.
          Charts and exports work identically on compacted data.
          {sensorRowCount > 0 && (
            <span style={{ display: "block", marginTop: "4px", color: "var(--color-text-muted)", fontSize: "12px" }}>
              Current: {sensorRowCount.toLocaleString()} readings. After full compaction: ~{estimatedCompacted.toLocaleString()} rows.
            </span>
          )}
        </p>

        {!showCompact ? (
          <button
            style={btnPrimary}
            onClick={() => setShowCompact(true)}
            disabled={sensorRowCount === 0}
          >
            Compact Readings...
          </button>
        ) : (
          <div style={{
            padding: "14px",
            border: "1px solid var(--color-warning)",
            borderRadius: "6px",
            background: "var(--color-bg-secondary)",
          }}>
            <div style={fieldGroup}>
              <label style={labelStyle}>Compact readings older than:</label>
              <input
                type="date"
                style={{ ...inputStyle, maxWidth: "200px" }}
                value={compactBefore}
                onChange={(e) => setCompactBefore(e.target.value)}
              />
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Type COMPACT to confirm:</label>
              <input
                type="text"
                style={{ ...inputStyle, maxWidth: "200px" }}
                value={compactConfirm}
                onChange={(e) => setCompactConfirm(e.target.value)}
                placeholder="COMPACT"
              />
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                style={{
                  ...btnPrimary,
                  background: "var(--color-warning)",
                  color: "#000",
                  opacity: compactLoading || compactConfirm !== "COMPACT" || !compactBefore ? 0.5 : 1,
                  cursor: compactLoading ? "wait" : "pointer",
                }}
                onClick={handleCompact}
                disabled={compactLoading || compactConfirm !== "COMPACT" || !compactBefore}
              >
                {compactLoading ? "Compacting..." : "Compact"}
              </button>
              <button
                style={{ ...btnPrimary, background: "var(--color-bg-card)", color: "var(--color-text)", border: "1px solid var(--color-border)" }}
                onClick={() => { setShowCompact(false); setCompactConfirm(""); setCompactBefore(""); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Backup Card */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Backup</h3>
        <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", fontFamily: "var(--font-body)", margin: "0 0 12px 0" }}>
          Complete SQLite database snapshot. Can be restored by replacing the database file.
        </p>
        <a
          href={getDbBackupUrl()}
          download
          style={{
            ...btnPrimary,
            display: "inline-block",
            textDecoration: "none",
          }}
        >
          Download Backup
        </a>
      </div>

      {/* Purge All (Nuclear) */}
      <div style={{
        ...cardStyle,
        padding: isMobile ? "12px" : "20px",
        border: showPurgeAll ? "2px solid var(--color-danger)" : "1px solid var(--color-border)",
      }}>
        <h3 style={{ ...sectionTitle, color: "var(--color-danger)" }}>Danger Zone</h3>

        {!showPurgeAll ? (
          <>
            <p style={{ fontSize: "13px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", margin: "0 0 12px 0" }}>
              Permanently delete all sensor readings, archives, nowcasts, knowledge base entries, and spray history.
              Configuration and product definitions are preserved.
            </p>
            <button
              style={{
                ...btnPrimary,
                background: "transparent",
                color: "var(--color-danger)",
                border: "1px solid var(--color-danger)",
              }}
              onClick={() => setShowPurgeAll(true)}
            >
              Purge All Data...
            </button>
          </>
        ) : (
          <>
            <div style={{
              fontSize: "14px",
              color: "var(--color-danger)",
              fontFamily: "var(--font-body)",
              fontWeight: 600,
              marginBottom: "12px",
              lineHeight: "1.5",
            }}>
              This will permanently delete ALL data from all tables except configuration and spray product definitions. This cannot be undone.
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Type DELETE DATABASE to confirm:</label>
              <input
                type="text"
                style={{ ...inputStyle, maxWidth: "250px" }}
                value={purgeAllConfirm}
                onChange={(e) => setPurgeAllConfirm(e.target.value)}
                placeholder="DELETE DATABASE"
              />
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                style={{
                  ...btnPrimary,
                  background: "var(--color-danger)",
                  opacity: purgeAllLoading || purgeAllConfirm !== "DELETE DATABASE" ? 0.5 : 1,
                  cursor: purgeAllLoading ? "wait" : "pointer",
                }}
                onClick={handlePurgeAll}
                disabled={purgeAllLoading || purgeAllConfirm !== "DELETE DATABASE"}
              >
                {purgeAllLoading ? "Deleting..." : "Delete All Data"}
              </button>
              <button
                style={{ ...btnPrimary, background: "var(--color-bg-secondary)", color: "var(--color-text)", border: "1px solid var(--color-border)" }}
                onClick={() => { setShowPurgeAll(false); setPurgeAllConfirm(""); }}
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

// --- Backup Tab ---

function BackupTab({ val, updateField, isMobile }: {
  val: (key: string) => string | number | boolean;
  updateField: (key: string, value: string | number | boolean) => void;
  isMobile: boolean;
}) {
  const [backups, setBackups] = useState<import("../api/types.ts").BackupInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [backingUp, setBackingUp] = useState(false);
  const [backupResult, setBackupResult] = useState<string | null>(null);
  const [telegramTesting, setTelegramTesting] = useState(false);
  const [telegramTestResult, setTelegramTestResult] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<string | null>(null);
  const [restoreConfirm, setRestoreConfirm] = useState("");
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreResult, setRestoreResult] = useState<string | null>(null);

  const loadBackups = useCallback(() => {
    setLoading(true);
    listBackups()
      .then(setBackups)
      .catch(() => setBackups([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadBackups(); }, [loadBackups]);

  const handleBackupNow = () => {
    setBackingUp(true);
    setBackupResult(null);
    triggerBackup()
      .then((m) => {
        setBackupResult(`Backup created: ${formatBytes(m.archive_size_bytes)} — ${Object.entries(m.row_counts).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ")}`);
        loadBackups();
      })
      .catch((e) => setBackupResult(`Error: ${e.message}`))
      .finally(() => setBackingUp(false));
  };

  const handleDelete = (name: string) => {
    deleteBackup(name)
      .then(() => { setDeleteConfirm(null); loadBackups(); })
      .catch((e) => alert(`Delete failed: ${e.message}`));
  };

  const handleRestore = async (name: string) => {
    setRestoreLoading(true);
    setRestoreResult(null);
    try {
      const url = getBackupDownloadUrl(name);
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
      const blob = await resp.blob();
      const formData = new FormData();
      formData.append("file", blob, name);
      const restoreResp = await fetch(
        `${API_BASE}/api/backup/restore?confirmation=RESTORE`,
        { method: "POST", body: formData },
      );
      if (!restoreResp.ok) {
        const err = await restoreResp.text();
        throw new Error(err);
      }
      setRestoreResult("Restore complete. Restart both the web app and logger daemon to use the restored data.");
      setRestoreTarget(null);
      setRestoreConfirm("");
    } catch (e: unknown) {
      setRestoreResult(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setRestoreLoading(false);
    }
  };

  const lastSuccess = String(val("backup_last_success") || "");
  const lastError = String(val("backup_last_error") || "");

  return (
    <>
      {/* Automatic Backups */}
      <div style={cardStyle}>
        <h3 style={sectionTitle}>Automatic Backups</h3>
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={checkboxLabel}>
              <input
                type="checkbox"
                checked={val("backup_enabled") === true}
                onChange={(e) => updateField("backup_enabled", e.target.checked)}
              />
              Enable automatic backups
            </label>
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Backup interval</label>
            <select
              style={selectStyle}
              value={String(val("backup_interval_hours") || 24)}
              onChange={(e) => updateField("backup_interval_hours", Number(e.target.value))}
            >
              <option value="6">Every 6 hours</option>
              <option value="12">Every 12 hours</option>
              <option value="24">Daily</option>
              <option value="48">Every 2 days</option>
              <option value="168">Weekly</option>
            </select>
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Keep last N backups</label>
            <input
              type="number"
              style={inputStyle}
              min={1}
              max={100}
              value={String(val("backup_retention_count") || 7)}
              onChange={(e) => updateField("backup_retention_count", Number(e.target.value))}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Scheduled time (optional)</label>
            <input
              type="time"
              style={inputStyle}
              value={String(val("backup_schedule_time") || "")}
              onChange={(e) => updateField("backup_schedule_time", e.target.value)}
            />
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "4px", fontFamily: "var(--font-body)" }}>
              HH:MM — run backup at this time daily. Leave blank for interval-from-boot.
            </span>
          </div>
        </div>
      </div>

      {/* Status & Manual Backup */}
      <div style={cardStyle}>
        <h3 style={sectionTitle}>Backup Status</h3>
        <div style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", marginBottom: "12px" }}>
          <div>Last successful backup: {lastSuccess ? new Date(lastSuccess).toLocaleString() : "Never"}</div>
          {lastError && (
            <div style={{ color: "var(--color-danger)", marginTop: "4px" }}>Last error: {lastError}</div>
          )}
        </div>
        <button
          style={{ ...btnPrimary, opacity: backingUp ? 0.6 : 1 }}
          onClick={handleBackupNow}
          disabled={backingUp}
        >
          {backingUp ? "Creating backup..." : "Backup Now"}
        </button>
        {backupResult && (
          <div style={{
            marginTop: "8px",
            padding: "8px 12px",
            borderRadius: "6px",
            fontSize: "13px",
            fontFamily: "var(--font-body)",
            background: backupResult.startsWith("Error") ? "rgba(211,47,47,0.1)" : "rgba(46,125,50,0.1)",
            border: backupResult.startsWith("Error") ? "1px solid var(--color-danger)" : "1px solid var(--color-success)",
            color: backupResult.startsWith("Error") ? "var(--color-danger)" : "var(--color-success)",
          }}>
            {backupResult}
          </div>
        )}
      </div>

      {/* Existing Backups */}
      <div style={cardStyle}>
        <h3 style={sectionTitle}>Existing Backups</h3>
        {loading ? (
          <div style={{ color: "var(--color-text-muted)", fontSize: "13px", fontFamily: "var(--font-body)" }}>Loading...</div>
        ) : backups.length === 0 ? (
          <div style={{ color: "var(--color-text-muted)", fontSize: "13px", fontFamily: "var(--font-body)" }}>No backups found.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "13px",
              fontFamily: "var(--font-body)",
            }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                  <th style={{ textAlign: "left", padding: "8px", color: "var(--color-text-secondary)" }}>Filename</th>
                  <th style={{ textAlign: "right", padding: "8px", color: "var(--color-text-secondary)" }}>Size</th>
                  <th style={{ textAlign: "right", padding: "8px", color: "var(--color-text-secondary)" }}>Date</th>
                  <th style={{ textAlign: "right", padding: "8px", color: "var(--color-text-secondary)" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.name} style={{ borderBottom: "1px solid var(--color-border)" }}>
                    <td style={{ padding: "8px", color: "var(--color-text)" }}>{b.name}</td>
                    <td style={{ padding: "8px", textAlign: "right", color: "var(--color-text-secondary)" }}>{formatBytes(b.size_bytes)}</td>
                    <td style={{ padding: "8px", textAlign: "right", color: "var(--color-text-secondary)" }}>{new Date(b.modified).toLocaleString()}</td>
                    <td style={{ padding: "8px", textAlign: "right", whiteSpace: "nowrap" }}>
                      <a
                        href={getBackupDownloadUrl(b.name)}
                        style={{ color: "var(--color-accent)", marginRight: "12px", textDecoration: "none", fontWeight: 600 }}
                      >
                        Download
                      </a>
                      {deleteConfirm === b.name ? (
                        <span>
                          <button
                            onClick={() => handleDelete(b.name)}
                            style={{ background: "var(--color-danger)", color: "#fff", border: "none", borderRadius: "4px", padding: "4px 10px", cursor: "pointer", fontSize: "12px", marginRight: "4px" }}
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            style={{ background: "var(--color-bg-secondary)", color: "var(--color-text-secondary)", border: "1px solid var(--color-border)", borderRadius: "4px", padding: "4px 10px", cursor: "pointer", fontSize: "12px" }}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirm(b.name)}
                          style={{ background: "none", border: "none", color: "var(--color-danger)", cursor: "pointer", fontWeight: 600, fontSize: "13px" }}
                        >
                          Delete
                        </button>
                      )}
                      {restoreTarget !== b.name && (
                        <button
                          onClick={() => { setRestoreTarget(b.name); setRestoreConfirm(""); setRestoreResult(null); }}
                          style={{ background: "none", border: "none", color: "var(--color-warning, #f59e0b)", cursor: "pointer", fontWeight: 600, fontSize: "13px", marginLeft: "12px" }}
                        >
                          Restore
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Restore confirmation dialog */}
        {restoreTarget && (
          <div style={{
            marginTop: "16px",
            padding: "16px",
            borderRadius: "8px",
            border: "2px solid var(--color-warning, #f59e0b)",
            background: "rgba(245,158,11,0.05)",
          }}>
            <div style={{ fontWeight: 600, fontSize: "14px", fontFamily: "var(--font-body)", color: "var(--color-text)", marginBottom: "8px" }}>
              Restore from {restoreTarget}
            </div>
            <div style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", marginBottom: "12px" }}>
              This will replace the current database. A .pre-restore copy will be created as a safety net.
              You must restart both the web app and logger daemon after restore.
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Type RESTORE to confirm:</label>
              <input
                type="text"
                style={{ ...inputStyle, maxWidth: "200px" }}
                value={restoreConfirm}
                onChange={(e) => setRestoreConfirm(e.target.value)}
                placeholder="RESTORE"
              />
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={() => handleRestore(restoreTarget)}
                disabled={restoreConfirm !== "RESTORE" || restoreLoading}
                style={{
                  ...btnPrimary,
                  background: restoreConfirm === "RESTORE" ? "var(--color-warning, #f59e0b)" : "var(--color-bg-secondary)",
                  color: restoreConfirm === "RESTORE" ? "#000" : "var(--color-text-muted)",
                  opacity: restoreLoading ? 0.6 : 1,
                }}
              >
                {restoreLoading ? "Restoring..." : "Restore"}
              </button>
              <button
                onClick={() => { setRestoreTarget(null); setRestoreConfirm(""); }}
                style={{ ...btnPrimary, background: "var(--color-bg-secondary)", color: "var(--color-text-secondary)" }}
              >
                Cancel
              </button>
            </div>
            {restoreResult && (
              <div style={{
                marginTop: "8px",
                padding: "8px 12px",
                borderRadius: "6px",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                background: restoreResult.startsWith("Error") ? "rgba(211,47,47,0.1)" : "rgba(46,125,50,0.1)",
                border: restoreResult.startsWith("Error") ? "1px solid var(--color-danger)" : "1px solid var(--color-success)",
                color: restoreResult.startsWith("Error") ? "var(--color-danger)" : "var(--color-success)",
              }}>
                {restoreResult}
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}


// --- System Log Tab ---

function SystemTab({ isMobile }: { isMobile: boolean }) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [levelFilter, setLevelFilter] = useState("WARNING");

  const load = useCallback(() => {
    setLoading(true);
    fetchLogs(levelFilter, 200)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [levelFilter]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 15 seconds
  useEffect(() => {
    const id = setInterval(() => {
      fetchLogs(levelFilter, 200).then(setEntries).catch(() => {});
    }, 15_000);
    return () => clearInterval(id);
  }, [levelFilter]);

  const levelColor = (lvl: string) => {
    switch (lvl) {
      case "CRITICAL": return "#ef4444";
      case "ERROR": return "#ef4444";
      case "WARNING": return "#f59e0b";
      default: return "var(--color-text-muted)";
    }
  };

  return (
    <>
      <div style={cardStyle}>
        <div style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "12px",
          flexWrap: "wrap",
          gap: "8px",
        }}>
          <h3 style={sectionTitle}>Application Logs</h3>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              style={{
                ...selectStyle,
                width: "auto",
                minWidth: "120px",
              }}
            >
              <option value="WARNING">WARNING+</option>
              <option value="ERROR">ERROR+</option>
              <option value="DEBUG">ALL</option>
            </select>
            <button
              onClick={load}
              disabled={loading}
              style={{
                fontFamily: "var(--font-body)",
                fontSize: "13px",
                padding: "6px 14px",
                borderRadius: "6px",
                border: "1px solid var(--color-border)",
                background: "var(--color-bg-secondary)",
                color: "var(--color-text-secondary)",
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.6 : 1,
              }}
            >
              Refresh
            </button>
          </div>
        </div>

        {entries.length === 0 && !loading && (
          <p style={{
            fontFamily: "var(--font-body)",
            fontSize: "14px",
            color: "var(--color-text-muted)",
            textAlign: "center",
            padding: "32px 0",
          }}>
            No log entries at this level.
          </p>
        )}

        {entries.length > 0 && (
          <div style={{
            maxHeight: isMobile ? "400px" : "500px",
            overflowY: "auto",
            border: "1px solid var(--color-border)",
            borderRadius: "6px",
            background: "var(--color-bg-secondary)",
          }}>
            {entries.map((entry, i) => (
              <div
                key={i}
                style={{
                  padding: "8px 12px",
                  borderBottom: i < entries.length - 1 ? "1px solid var(--color-border)" : undefined,
                  fontFamily: "var(--font-mono)",
                  fontSize: "12px",
                  lineHeight: 1.5,
                }}
              >
                <div style={{
                  display: "flex",
                  gap: "8px",
                  alignItems: "baseline",
                  flexWrap: "wrap",
                }}>
                  <span style={{ color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                    {new Date(entry.timestamp).toLocaleString()}
                  </span>
                  <span style={{
                    color: levelColor(entry.level),
                    fontWeight: 600,
                    fontSize: "11px",
                    padding: "1px 6px",
                    borderRadius: "3px",
                    background: `${levelColor(entry.level)}22`,
                  }}>
                    {entry.level}
                  </span>
                  <span style={{ color: "var(--color-text-secondary)" }}>
                    {entry.logger}
                  </span>
                </div>
                <div style={{
                  color: "var(--color-text)",
                  marginTop: "2px",
                  wordBreak: "break-word",
                }}>
                  {entry.message}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Service restart instructions */}
      <div style={cardStyle}>
        <h3 style={{
          margin: "0 0 12px 0",
          fontSize: "16px",
          fontFamily: "var(--font-heading)",
          color: "var(--color-text)",
        }}>
          Service Management
        </h3>
        <p style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", marginTop: 0, lineHeight: 1.5 }}>
          Most settings take effect immediately or on the next cycle. To apply driver or connection changes, use <strong>Save &amp; Reconnect</strong> on the Station tab.
        </p>
        <p style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", marginTop: "8px", lineHeight: 1.5 }}>
          If a full service restart is needed:
        </p>
        <div style={{
          background: "var(--color-bg-secondary)",
          borderRadius: "6px",
          padding: "12px",
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: "12px",
          color: "var(--color-text)",
          marginTop: "8px",
          lineHeight: 1.6,
        }}>
          <div style={{ marginBottom: "8px", color: "var(--color-text-muted)", fontSize: "11px" }}>Windows (services):</div>
          <div>net stop KanfeiWeb &amp;&amp; net stop KanfeiLogger</div>
          <div>net start KanfeiLogger &amp;&amp; net start KanfeiWeb</div>
          <div style={{ marginTop: "12px", marginBottom: "8px", color: "var(--color-text-muted)", fontSize: "11px" }}>Linux (systemd):</div>
          <div>sudo systemctl restart kanfei-logger kanfei-web</div>
          <div style={{ marginTop: "12px", marginBottom: "8px", color: "var(--color-text-muted)", fontSize: "11px" }}>Manual (dev mode):</div>
          <div>Ctrl+C both terminals, then restart</div>
        </div>
      </div>
    </>
  );
}

// --- Component ---

export default function Settings() {
  const isMobile = useIsMobile();
  const [configItems, setConfigItems] = useState<ConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [reconnectMsg, setReconnectMsg] = useState<string | null>(null);
  const [ports, setPorts] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<"station" | "display" | "services" | "alerts" | "nowcast" | "spray" | "usage" | "database" | "backup" | "system">("station");

  const { flags, refresh: refreshFeatureFlags } = useFeatureFlags();
  const { themeName, setThemeName } = useTheme();
  const [timezone, setTimezoneState] = useState(getTimezone);
  const {
    enabled: bgEnabled,
    setEnabled: setBgEnabled,
    intensity: bgIntensity,
    setIntensity: setBgIntensity,
    transparency: bgTransparency,
    setTransparency: setBgTransparency,
    customImages: bgCustomImages,
    refreshCustomImages: refreshBgImages,
  } = useWeatherBackground();
  const [scenesExpanded, setScenesExpanded] = useState(false);

  // --- Nowcast presets (tier-gated from server) ---
  const [presetOptions, setPresetOptions] = useState<NowcastPresetOption[]>([]);
  useEffect(() => {
    if (flags.nowcastEnabled) {
      fetchNowcastPresets()
        .then((resp) => setPresetOptions(resp.available))
        .catch(() => {});
    }
  }, [flags.nowcastEnabled]);

  // --- Nowcast disclaimer ---
  const [showNowcastDisclaimer, setShowNowcastDisclaimer] = useState(false);
  const [disclaimerCountdown, setDisclaimerCountdown] = useState(0);

  useEffect(() => {
    if (!showNowcastDisclaimer) return;
    setDisclaimerCountdown(5);
    const id = setInterval(() => {
      setDisclaimerCountdown((c) => {
        if (c <= 1) { clearInterval(id); return 0; }
        return c - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [showNowcastDisclaimer]);

  // --- Alert thresholds ---
  const [alertThresholds, setAlertThresholds] = useState<AlertThreshold[]>([]);
  const [alertSaving, setAlertSaving] = useState(false);
  const [alertSuccess, setAlertSuccess] = useState(false);
  const [showAddAlert, setShowAddAlert] = useState(false);
  const [newAlert, setNewAlert] = useState<Partial<AlertThreshold>>({
    sensor: "outside_temp",
    operator: "<=",
    value: 32,
    label: "",
    cooldown_min: 15,
    enabled: true,
  });

  const handleBgUpload = useCallback(async (scene: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const resp = await fetch(`${API_BASE}/api/backgrounds/${scene}`, {
        method: "POST",
        body: form,
      });
      if (resp.ok) {
        refreshBgImages();
      }
    } catch {
      /* ignore */
    }
  }, [refreshBgImages]);

  const handleBgDelete = useCallback(async (scene: string) => {
    try {
      const resp = await fetch(`${API_BASE}/api/backgrounds/${scene}`, {
        method: "DELETE",
      });
      if (resp.ok) {
        refreshBgImages();
      }
    } catch {
      /* ignore */
    }
  }, [refreshBgImages]);

  // WeatherLink hardware config state
  const [wlConfig, setWlConfig] = useState<WeatherLinkConfig | null>(null);
  const [wlArchivePeriod, setWlArchivePeriod] = useState<number>(30);
  const [wlSamplePeriod, setWlSamplePeriod] = useState<number>(60);
  const [wlCal, setWlCal] = useState<WeatherLinkCalibration>({
    inside_temp: 0, outside_temp: 0, barometer: 0, outside_humidity: 0, rain_cal: 100,
  });
  const [wlSaving, setWlSaving] = useState(false);
  const [wlMsg, setWlMsg] = useState<string | null>(null);
  const [wlError, setWlError] = useState<string | null>(null);

  // Load config + serial ports (fast), then weatherlink config (slow, non-blocking)
  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetchConfig(),
      fetchSerialPorts().catch(() => ({ ports: [] })),
    ])
      .then(([items, portResult]) => {
        setConfigItems(items);
        setPorts(portResult.ports);
        setLoading(false);
        // Load alert thresholds from config
        const atItem = items.find((i: ConfigItem) => i.key === "alert_thresholds");
        if (atItem && typeof atItem.value === "string") {
          try { setAlertThresholds(JSON.parse(atItem.value)); } catch { /* ignore */ }
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });

    // Load WeatherLink hardware config in background (serial I/O is slow)
    fetchWeatherLinkConfig()
      .then((wl) => {
        if (wl && !("error" in wl)) {
          setWlConfig(wl);
          if (wl.archive_period != null) setWlArchivePeriod(wl.archive_period);
          if (wl.sample_period != null) setWlSamplePeriod(wl.sample_period);
          setWlCal(wl.calibration);
        }
      })
      .catch(() => {});
  }, []);

  // Reset active tab if the current tab's feature gets disabled.
  useEffect(() => {
    if (activeTab === "nowcast" && !flags.nowcastEnabled) setActiveTab("station");
    if (activeTab === "spray" && !flags.sprayEnabled) setActiveTab("station");
    if (activeTab === "usage" && !flags.nowcastEnabled) setActiveTab("station");
  }, [flags.nowcastEnabled, flags.sprayEnabled, activeTab]);

  // Take over the parent scroll container so the header stays fixed
  // and only the tab content scrolls (single scrollbar).
  // Uses dynamic measurement to set a definite height on Settings,
  // bypassing the broken flex height chain (grid uses minHeight, not height).
  // Suppress parent scroll via CSS class (immune to React re-renders)
  // and dynamically measure height so the internal flex layout works.
  const settingsRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (loading) return;
    const el = settingsRef.current;
    if (!el) return;
    document.body.classList.add("settings-scroll-lock");
    const update = () => {
      const top = el.getBoundingClientRect().top;
      el.style.height = `${window.innerHeight - top}px`;
    };
    requestAnimationFrame(update);
    window.addEventListener("resize", update);
    return () => {
      document.body.classList.remove("settings-scroll-lock");
      window.removeEventListener("resize", update);
    };
  }, [loading]);

  const updateField = useCallback(
    (key: string, value: string | number | boolean) => {
      setConfigItems((prev) => setConfigValue(prev, key, value));
      setSaveSuccess(false);
    },
    [],
  );

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setSaveSuccess(false);
    try {
      // Ensure station_timezone is always populated for backend services.
      let items = configItems;
      const tzVal = getConfigValue(items, "station_timezone");
      if (!tzVal) {
        items = setConfigValue(items, "station_timezone", resolveTimezone());
      }
      // Exclude ui_* keys — those are owned by their context providers
      items = items.filter((i) => !i.key.startsWith("ui_"));
      const updated = await updateConfig(items);
      setConfigItems(updated);
      setSaveSuccess(true);
      await refreshFeatureFlags();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }, [configItems, refreshFeatureFlags]);

  const handleSaveAndReconnect = useCallback(async () => {
    setSaving(true);
    setReconnecting(true);
    setError(null);
    setSaveSuccess(false);
    setReconnectMsg(null);
    try {
      let items = configItems;
      const tzVal = getConfigValue(items, "station_timezone");
      if (!tzVal) {
        items = setConfigValue(items, "station_timezone", resolveTimezone());
      }
      // Exclude ui_* keys — those are owned by their context providers
      items = items.filter((i) => !i.key.startsWith("ui_"));
      const updated = await updateConfig(items);
      setConfigItems(updated);
      const result = await reconnectStation();
      if (result.success) {
        setReconnectMsg(
          `Reconnected: ${result.station_type ?? "station"} detected`,
        );
      } else {
        setError(result.error ?? "Reconnect failed");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
      setReconnecting(false);
    }
  }, [configItems]);

  const refreshPorts = useCallback(() => {
    fetchSerialPorts()
      .then((result) => setPorts(result.ports))
      .catch(() => {});
  }, []);

  const handleWlSave = useCallback(async () => {
    setWlSaving(true);
    setWlMsg(null);
    setWlError(null);
    try {
      const update: Record<string, unknown> = {};
      if (wlConfig === null || wlArchivePeriod !== wlConfig.archive_period) {
        update.archive_period = wlArchivePeriod;
      }
      if (wlConfig === null || wlSamplePeriod !== wlConfig.sample_period) {
        update.sample_period = wlSamplePeriod;
      }
      const calChanged = wlConfig === null ||
        wlCal.inside_temp !== wlConfig.calibration.inside_temp ||
        wlCal.outside_temp !== wlConfig.calibration.outside_temp ||
        wlCal.barometer !== wlConfig.calibration.barometer ||
        wlCal.outside_humidity !== wlConfig.calibration.outside_humidity ||
        wlCal.rain_cal !== wlConfig.calibration.rain_cal;
      if (calChanged) {
        update.calibration = wlCal;
      }
      if (Object.keys(update).length === 0) {
        setWlMsg("No changes to save");
        setWlSaving(false);
        return;
      }
      const resp = await updateWeatherLinkConfig(update);
      if ("error" in resp) {
        setWlError(String((resp as Record<string, unknown>).error));
        return;
      }
      if (resp.config) {
        setWlConfig(resp.config);
        setWlCal(resp.config.calibration);
        if (resp.config.archive_period != null) setWlArchivePeriod(resp.config.archive_period);
        if (resp.config.sample_period != null) setWlSamplePeriod(resp.config.sample_period);
      }
      const failures = Object.entries(resp.results).filter(([, v]) => v !== "ok");
      if (failures.length > 0) {
        setWlError("Partial failure: " + failures.map(([k, v]) => `${k}: ${v}`).join(", "));
      } else {
        setWlMsg("Saved to WeatherLink");
      }
    } catch (err: unknown) {
      setWlError(err instanceof Error ? err.message : String(err));
    } finally {
      setWlSaving(false);
    }
  }, [wlConfig, wlArchivePeriod, wlSamplePeriod, wlCal]);

  const handleClearRainDaily = useCallback(async () => {
    if (!confirm("Clear the daily rain accumulator? This cannot be undone.")) return;
    setWlMsg(null);
    setWlError(null);
    try {
      const resp = await clearRainDaily();
      setWlMsg(resp.success ? "Daily rain cleared" : "Failed to clear daily rain");
    } catch (err: unknown) {
      setWlError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const handleClearRainYearly = useCallback(async () => {
    if (!confirm("Clear the yearly rain accumulator? This cannot be undone.")) return;
    setWlMsg(null);
    setWlError(null);
    try {
      const resp = await clearRainYearly();
      setWlMsg(resp.success ? "Yearly rain cleared" : "Failed to clear yearly rain");
    } catch (err: unknown) {
      setWlError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const handleForceArchive = useCallback(async () => {
    setWlMsg(null);
    setWlError(null);
    try {
      const resp = await forceArchive();
      setWlMsg(resp.success ? "Archive record written" : "Failed to write archive");
    } catch (err: unknown) {
      setWlError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  // Convenience getters
  const val = (key: string) => getConfigValue(configItems, key);

  if (loading) {
    return (
      <div>
        <h2
          style={{
            margin: "0 0 16px 0",
            fontSize: "24px",
            fontFamily: "var(--font-heading)",
            color: "var(--color-text)",
          }}
        >
          Settings
        </h2>
        <div
          style={{
            ...cardStyle,
            display: "flex",
            justifyContent: "center",
            padding: "48px",
          }}
        >
          <div
            style={{
              width: "36px",
              height: "36px",
              border: "3px solid var(--color-border)",
              borderTopColor: "var(--color-accent)",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }}
          />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  return (
    <div ref={settingsRef} style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Fixed header: heading + tab bar + save buttons */}
      <div style={{
        flexShrink: 0,
        padding: "0 24px 12px",
      }}>
      <h2
        style={{
          margin: "0 0 12px 0",
          fontSize: "24px",
          fontFamily: "var(--font-heading)",
          color: "var(--color-text)",
        }}
      >
        Settings
      </h2>

      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        flexWrap: "wrap",
      }}>
        {([
          ["station", "Station"],
          ["display", "Display"],
          ["services", "Services"],
          ["alerts", "Alerts"],
          ...(flags.nowcastEnabled ? [["nowcast", "Nowcast"] as const] : []),
          ...(flags.sprayEnabled ? [["spray", "Spray"] as const] : []),
          ...(flags.nowcastEnabled ? [["usage", "Usage"] as const] : []),
          ["database", "Database"],
          ["backup", "Backup"],
          ["system", "System"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "14px",
              padding: isMobile ? "8px 14px" : "8px 20px",
              borderRadius: "6px",
              border: "1px solid var(--color-border)",
              background: activeTab === key ? "var(--color-accent)" : "var(--color-bg-secondary)",
              color: activeTab === key ? "#fff" : "var(--color-text-secondary)",
              cursor: "pointer",
              transition: "background 0.15s ease, color 0.15s ease",
            }}
          >
            {label}
          </button>
        ))}

        <span style={{ flex: 1 }} />

        {saveSuccess && (
          <span style={{ color: "var(--color-success)", fontSize: "13px", fontFamily: "var(--font-body)" }}>
            Saved.
          </span>
        )}
        {reconnectMsg && (
          <span style={{ color: "var(--color-success)", fontSize: "13px", fontFamily: "var(--font-body)" }}>
            {reconnectMsg}
          </span>
        )}
        {error && (
          <span style={{ color: "var(--color-danger)", fontSize: "13px", fontFamily: "var(--font-body)" }}>
            Error: {error}
          </span>
        )}

        <button
          style={{
            ...btnPrimary,
            fontSize: "13px",
            padding: "8px 16px",
            opacity: saving ? 0.6 : 1,
            cursor: saving ? "wait" : "pointer",
          }}
          onClick={handleSave}
          disabled={saving || reconnecting}
        >
          {saving && !reconnecting ? "Saving..." : "Save"}
        </button>

        <button
          style={{
            ...btnPrimary,
            fontSize: "13px",
            padding: "8px 16px",
            background: "var(--color-bg-secondary)",
            color: "var(--color-text)",
            border: "1px solid var(--color-border)",
            opacity: reconnecting ? 0.6 : 1,
            cursor: reconnecting ? "wait" : "pointer",
          }}
          onClick={handleSaveAndReconnect}
          disabled={saving || reconnecting}
        >
          {reconnecting ? "Reconnecting..." : "Save & Reconnect"}
        </button>
      </div>
      </div>

      {/* Scrollable tab content — no padding here so scrollbar sits at page edge */}
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
      <div style={{ padding: "16px 24px 24px" }}>

      {activeTab === "station" && (<>
      {/* Optional Features */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Optional Features</h3>
        <p style={{ fontSize: "13px", color: "var(--color-text-muted)", marginBottom: "16px", fontFamily: "var(--font-body)", marginTop: 0 }}>
          Enable optional features to add their pages and settings tabs.
        </p>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("nowcast_enabled") === true}
              onChange={(e) => {
                if (e.target.checked && val("nowcast_disclaimer_accepted") !== true) {
                  setShowNowcastDisclaimer(true);
                } else {
                  updateField("nowcast_enabled", e.target.checked);
                }
              }}
            />
            AI Nowcast
          </label>
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px", fontFamily: "var(--font-body)" }}>
            Hyper-local AI-powered weather forecasting using Claude. Requires an Anthropic API key.
          </span>
        </div>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("spray_enabled") === true}
              onChange={(e) => updateField("spray_enabled", e.target.checked)}
            />
            Spray Advisor
          </label>
          <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px", fontFamily: "var(--font-body)" }}>
            Agricultural spray application recommendations based on weather conditions and product constraints.
          </span>
        </div>
      </div>

      {/* Nowcast disclaimer modal */}
      {showNowcastDisclaimer && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 200,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "var(--color-bg-card-solid, var(--color-bg-card))",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--gauge-border-radius, 16px)",
              boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
              padding: isMobile ? "16px" : "24px",
              width: "92vw",
              maxWidth: 520,
              maxHeight: "80vh",
              overflowY: "auto",
            }}
          >
            <h3
              style={{
                margin: "0 0 16px 0",
                fontSize: "18px",
                fontFamily: "var(--font-heading)",
                color: "var(--color-text)",
              }}
            >
              AI Nowcast — Important Notice
            </h3>
            <div
              style={{
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                lineHeight: "1.6",
                marginBottom: "20px",
              }}
            >
              <p style={{ margin: "0 0 12px 0" }}>
                The AI Nowcast feature provides <strong>experimental, AI-generated</strong> weather
                analysis. Please read and acknowledge the following before enabling:
              </p>
              <ul style={{ margin: "0 0 12px 0", paddingLeft: "20px" }}>
                <li style={{ marginBottom: "8px" }}>
                  This is <strong>supplemental to, not a substitute for</strong>, official
                  National Weather Service (NWS) warnings and forecasts.
                </li>
                <li style={{ marginBottom: "8px" }}>
                  There is <strong>no guarantee of accuracy, timeliness, or completeness</strong>.
                  AI analysis may contain errors or miss critical weather developments.
                </li>
                <li style={{ marginBottom: "8px" }}>
                  <strong>Always follow official NWS guidance first</strong>, especially during
                  severe weather events.
                </li>
                <li style={{ marginBottom: "8px" }}>
                  By enabling this feature, <strong>you assume full responsibility</strong> for
                  any decisions made based on its output.
                </li>
              </ul>
              <p style={{ margin: 0 }}>
                Nowcast requires an Anthropic API key and will incur usage costs based on the
                selected model and update interval.
              </p>
            </div>
            <div style={{ display: "flex", gap: "12px", justifyContent: "flex-end" }}>
              <button
                style={{
                  fontFamily: "var(--font-body)",
                  fontSize: "14px",
                  padding: "10px 20px",
                  borderRadius: "6px",
                  border: "1px solid var(--color-border)",
                  background: "var(--color-bg-secondary)",
                  color: "var(--color-text)",
                  cursor: "pointer",
                }}
                onClick={() => setShowNowcastDisclaimer(false)}
              >
                Cancel
              </button>
              <button
                disabled={disclaimerCountdown > 0}
                style={{
                  ...btnPrimary,
                  padding: "10px 20px",
                  opacity: disclaimerCountdown > 0 ? 0.5 : 1,
                  cursor: disclaimerCountdown > 0 ? "not-allowed" : "pointer",
                }}
                onClick={() => {
                  if (disclaimerCountdown > 0) return;
                  updateField("nowcast_disclaimer_accepted", true);
                  updateField("nowcast_enabled", true);
                  setShowNowcastDisclaimer(false);
                }}
              >
                {disclaimerCountdown > 0
                  ? `Please read (${disclaimerCountdown}s)`
                  : "I Understand and Accept"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Station section — driver-aware */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Station</h3>
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Driver Type</label>
            <select
              style={selectStyle}
              value={String(val("station_driver_type") || "legacy")}
              onChange={(e) => updateField("station_driver_type", e.target.value)}
            >
              <option value="legacy">Davis Weather Monitor / Wizard (serial)</option>
              <option value="vantage">Davis Vantage Pro / Pro2 / Vue (serial)</option>
              <option value="weatherlink_ip">Davis WeatherLink IP (TCP)</option>
              <option value="weatherlink_live">Davis WeatherLink Live (HTTP)</option>
              <option value="ecowitt">Ecowitt / Fine Offset (LAN)</option>
              <option value="tempest">WeatherFlow Tempest (UDP)</option>
              <option value="ambient">Ambient Weather (HTTP push)</option>
            </select>
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "4px", fontFamily: "var(--font-body)" }}>
              Click <strong>Save &amp; Reconnect</strong> after changing to apply the new driver.
            </span>
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Poll Interval (seconds)</label>
            <input
              style={readOnlyInput}
              value={String(val("poll_interval"))}
              readOnly
              tabIndex={-1}
            />
          </div>
        </div>

        {/* Serial config — legacy and vantage */}
        {["legacy", "vantage"].includes(String(val("station_driver_type") || "legacy")) && (
          <div style={{ ...gridTwoCol(isMobile), marginTop: "12px" }}>
            <div style={fieldGroup}>
              <label style={labelStyle}>
                Serial Port
                <button
                  style={{
                    fontSize: "11px",
                    padding: "2px 8px",
                    marginLeft: "8px",
                    borderRadius: "4px",
                    border: "1px solid var(--color-border)",
                    background: "var(--color-bg-secondary)",
                    color: "var(--color-text)",
                    cursor: "pointer",
                    fontFamily: "var(--font-body)",
                  }}
                  onClick={refreshPorts}
                >
                  Refresh
                </button>
              </label>
              <select
                style={selectStyle}
                value={String(val("serial_port"))}
                onChange={(e) => updateField("serial_port", e.target.value)}
              >
                {ports.length === 0 && (
                  <option value="">No ports detected</option>
                )}
                {ports.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
                {val("serial_port") && !ports.includes(String(val("serial_port"))) && (
                  <option value={String(val("serial_port"))}>{String(val("serial_port"))}</option>
                )}
              </select>
            </div>
            <div style={fieldGroup}>
              <label style={labelStyle}>Baud Rate</label>
              <select
                style={selectStyle}
                value={String(val("baud_rate"))}
                onChange={(e) => updateField("baud_rate", parseInt(e.target.value))}
              >
                <option value="19200">19200 (Vantage Pro/Pro2/Vue)</option>
                <option value="2400">2400 (Weather Monitor/Wizard)</option>
                <option value="1200">1200</option>
              </select>
            </div>
          </div>
        )}

        {/* Network config — WeatherLink IP/Live, Ecowitt */}
        {["weatherlink_ip", "weatherlink_live", "ecowitt"].includes(String(val("station_driver_type"))) && (
          <div style={{ ...gridTwoCol(isMobile), marginTop: "12px" }}>
            <div style={fieldGroup}>
              <label style={labelStyle}>
                {String(val("station_driver_type")) === "ecowitt" ? "Gateway" : "Device"} IP Address
              </label>
              <input
                style={inputStyle}
                type="text"
                placeholder="192.168.1.100"
                value={String(val(String(val("station_driver_type")) === "ecowitt" ? "ecowitt_ip" : "weatherlink_ip") || "")}
                onChange={(e) => updateField(
                  String(val("station_driver_type")) === "ecowitt" ? "ecowitt_ip" : "weatherlink_ip",
                  e.target.value,
                )}
              />
            </div>
            {String(val("station_driver_type")) === "weatherlink_ip" && (
              <div style={fieldGroup}>
                <label style={labelStyle}>TCP Port</label>
                <input
                  style={inputStyle}
                  type="number"
                  value={String(val("weatherlink_port") || 22222)}
                  onChange={(e) => updateField("weatherlink_port", parseInt(e.target.value) || 22222)}
                />
              </div>
            )}
          </div>
        )}

        {/* Tempest config */}
        {String(val("station_driver_type")) === "tempest" && (
          <div style={{ marginTop: "12px" }}>
            <div style={fieldGroup}>
              <label style={labelStyle}>Hub Serial Number (optional)</label>
              <input
                style={inputStyle}
                type="text"
                placeholder="Leave blank to accept any hub"
                value={String(val("tempest_hub_sn") || "")}
                onChange={(e) => updateField("tempest_hub_sn", e.target.value)}
              />
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "4px", fontFamily: "var(--font-body)" }}>
                The Tempest hub broadcasts on your local network automatically.
              </span>
            </div>
          </div>
        )}

        {/* Ambient config */}
        {String(val("station_driver_type")) === "ambient" && (
          <div style={{ marginTop: "12px" }}>
            <div style={fieldGroup}>
              <label style={labelStyle}>Listen Port</label>
              <input
                style={inputStyle}
                type="number"
                value={String(val("ambient_listen_port") || 8080)}
                onChange={(e) => updateField("ambient_listen_port", parseInt(e.target.value) || 8080)}
              />
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "4px", fontFamily: "var(--font-body)" }}>
                Configure your station to push data to this computer's IP on this port.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* WeatherLink section — only for Davis serial drivers */}
      {["legacy", "vantage"].includes(String(val("station_driver_type") || "legacy")) && (
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>WeatherLink</h3>

        {/* Timing row */}
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={labelStyle} title="How often the WeatherLink saves a summary record to its internal memory. Shorter intervals give finer history but fill the buffer faster.">
              Archive Period (minutes)
            </label>
            <select
              style={selectStyle}
              value={wlArchivePeriod}
              onChange={(e) => setWlArchivePeriod(parseInt(e.target.value))}
            >
              {[1, 5, 10, 15, 30, 60, 120].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle} title="How often the WeatherLink reads sensors. Lower values give fresher LOOP data but increase processing load.">
              Sample Period (seconds)
            </label>
            <input
              style={inputStyle}
              type="number"
              min={1}
              max={255}
              value={wlSamplePeriod}
              onChange={(e) => {
                const v = parseInt(e.target.value);
                if (!isNaN(v) && v >= 1 && v <= 255) setWlSamplePeriod(v);
              }}
            />
          </div>
        </div>

        {/* Calibration row */}
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={labelStyle} title="Added to raw inside temperature reading (tenths of °F). Use to correct a known sensor bias.">
              Inside Temp Offset (tenths °F)
            </label>
            <input
              style={inputStyle}
              type="number"
              value={wlCal.inside_temp}
              onChange={(e) => setWlCal({ ...wlCal, inside_temp: parseInt(e.target.value) || 0 })}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle} title="Added to raw outside temperature reading (tenths of °F).">
              Outside Temp Offset (tenths °F)
            </label>
            <input
              style={inputStyle}
              type="number"
              value={wlCal.outside_temp}
              onChange={(e) => setWlCal({ ...wlCal, outside_temp: parseInt(e.target.value) || 0 })}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle} title="Subtracted from raw barometer reading (thousandths inHg). Adjust to match a known reference.">
              Barometer Offset (thousandths inHg)
            </label>
            <input
              style={inputStyle}
              type="number"
              value={wlCal.barometer}
              onChange={(e) => setWlCal({ ...wlCal, barometer: parseInt(e.target.value) || 0 })}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle} title="Added to raw outside humidity reading (%). Result is clamped to 1-100%.">
              Humidity Offset (%)
            </label>
            <input
              style={inputStyle}
              type="number"
              value={wlCal.outside_humidity}
              onChange={(e) => setWlCal({ ...wlCal, outside_humidity: parseInt(e.target.value) || 0 })}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle} title="Rain collector clicks per inch. Standard: 100 (0.01&quot;/click). Metric: 127. Do not change unless you have a non-standard collector.">
              Rain Calibration (clicks/inch)
            </label>
            <input
              style={inputStyle}
              type="number"
              value={wlCal.rain_cal}
              onChange={(e) => setWlCal({ ...wlCal, rain_cal: parseInt(e.target.value) || 100 })}
            />
          </div>
        </div>

        {/* Actions row */}
        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr 1fr" : "auto auto auto auto",
          gap: isMobile ? "8px" : "12px",
          marginTop: "8px",
          alignItems: "center",
        }}>
          <button
            style={{
              ...btnPrimary,
              opacity: wlSaving ? 0.6 : 1,
              cursor: wlSaving ? "wait" : "pointer",
              ...(isMobile ? { gridColumn: "1 / -1", fontSize: "13px", padding: "8px 12px" } : {}),
            }}
            onClick={handleWlSave}
            disabled={wlSaving}
            title="Write the above settings to the WeatherLink hardware"
          >
            {wlSaving ? "Saving..." : "Save to WeatherLink"}
          </button>

          <button
            style={{
              ...btnPrimary,
              background: "var(--color-bg-secondary)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              ...(isMobile ? { fontSize: "13px", padding: "8px 12px" } : {}),
            }}
            onClick={handleForceArchive}
            title="Immediately write current conditions to the archive buffer, regardless of the archive timer"
          >
            Force Archive
          </button>

          <button
            style={{
              ...btnPrimary,
              background: "var(--color-bg-secondary)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              ...(isMobile ? { fontSize: "13px", padding: "8px 12px" } : {}),
            }}
            onClick={handleClearRainDaily}
            title="Reset the daily rain accumulator to zero"
          >
            Clear Daily Rain
          </button>

          <button
            style={{
              ...btnPrimary,
              background: "var(--color-bg-secondary)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              ...(isMobile ? { fontSize: "13px", padding: "8px 12px" } : {}),
            }}
            onClick={handleClearRainYearly}
            title="Reset the yearly rain accumulator to zero"
          >
            Clear Yearly Rain
          </button>

          {wlMsg && (
            <span style={{ color: "var(--color-success)", fontSize: "14px", fontFamily: "var(--font-body)", gridColumn: "1 / -1" }}>
              {wlMsg}
            </span>
          )}
          {wlError && (
            <span style={{ color: "var(--color-danger)", fontSize: "14px", fontFamily: "var(--font-body)", gridColumn: "1 / -1" }}>
              Error: {wlError}
            </span>
          )}
        </div>
      </div>
      )}

      {/* Location section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Location</h3>
        <StepLocation
          latitude={Number(val("latitude")) || 0}
          longitude={Number(val("longitude")) || 0}
          elevation={Number(val("elevation")) || 0}
          onChange={(partial) => {
            if (partial.latitude !== undefined) updateField("latitude", partial.latitude);
            if (partial.longitude !== undefined) updateField("longitude", partial.longitude);
            if (partial.elevation !== undefined) updateField("elevation", partial.elevation);
          }}
        />
      </div>
      </>)}

      {activeTab === "display" && (<>
      {/* Units section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Units</h3>

        <div style={fieldGroup}>
          <label style={labelStyle}>Temperature</label>
          <div style={radioGroup}>
            {["F", "C"].map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="temp_unit"
                  checked={val("temp_unit") === u}
                  onChange={() => updateField("temp_unit", u)}
                />
                {u === "F" ? "Fahrenheit (\u00B0F)" : "Celsius (\u00B0C)"}
              </label>
            ))}
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Pressure</label>
          <div style={radioGroup}>
            {["inHg", "hPa"].map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="pressure_unit"
                  checked={val("pressure_unit") === u}
                  onChange={() => updateField("pressure_unit", u)}
                />
                {u === "inHg" ? "Inches of Mercury (inHg)" : "Hectopascals (hPa)"}
              </label>
            ))}
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Wind Speed</label>
          <div style={radioGroup}>
            {["mph", "kph", "knots"].map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="wind_unit"
                  checked={val("wind_unit") === u}
                  onChange={() => updateField("wind_unit", u)}
                />
                {u === "mph" ? "Miles per hour" : u === "kph" ? "Kilometers per hour" : "Knots"}
              </label>
            ))}
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Rain</label>
          <div style={radioGroup}>
            {["in", "mm"].map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="rain_unit"
                  checked={val("rain_unit") === u}
                  onChange={() => updateField("rain_unit", u)}
                />
                {u === "in" ? "Inches" : "Millimeters"}
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Display section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Display</h3>
        <div style={fieldGroup}>
          <label style={labelStyle}>Theme</label>
          <select
            style={selectStyle}
            value={themeName}
            onChange={(e) => setThemeName(e.target.value)}
          >
            {Object.entries(themes).map(([key, t]) => (
              <option key={key} value={key}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Timezone</label>
          <select
            style={selectStyle}
            value={timezone}
            onChange={(e) => {
              const tz = e.target.value;
              setTimezoneState(tz);
              storeTimezone(tz);
              // Also save resolved IANA name to backend for nowcast service
              const resolved = tz === "auto"
                ? Intl.DateTimeFormat().resolvedOptions().timeZone
                : tz;
              updateField("station_timezone", resolved);
            }}
          >
            <option value="auto">Auto ({resolveTimezone()})</option>
            {getTimezoneOptions().map((tz) => (
              <option key={tz} value={tz}>{tz.replace(/_/g, " ")}</option>
            ))}
          </select>
        </div>

        <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "16px", marginTop: "8px" }}>
          <div style={fieldGroup}>
            <label style={checkboxLabel}>
              <input
                type="checkbox"
                checked={bgEnabled}
                onChange={(e) => setBgEnabled(e.target.checked)}
              />
              Weather Background
            </label>
          </div>

          {bgEnabled && (
            <>
              <div style={fieldGroup}>
                <label style={labelStyle} title="How visible the weather background is. Higher values show more of the gradient/image.">
                  Intensity: {bgIntensity}%
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={bgIntensity}
                  onChange={(e) => setBgIntensity(parseInt(e.target.value))}
                  style={{ width: "100%", cursor: "pointer" }}
                />
              </div>

              <div style={fieldGroup}>
                <label style={labelStyle} title="How transparent tiles, cards, header, and sidebar are. Higher values let more of the background show through.">
                  Tile Transparency: {bgTransparency}%
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  value={bgTransparency}
                  onChange={(e) => setBgTransparency(parseInt(e.target.value))}
                  style={{ width: "100%", cursor: "pointer" }}
                />
              </div>

              <div style={fieldGroup}>
                <label
                  style={{ ...labelStyle, cursor: "pointer", userSelect: "none" }}
                  onClick={() => setScenesExpanded((v) => !v)}
                >
                  Custom Scene Images {scenesExpanded ? "\u25B2" : "\u25BC"}
                </label>

                {scenesExpanded && (
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(auto-fill, minmax(200px, 1fr))",
                    gap: isMobile ? "8px" : "12px",
                    marginTop: "8px",
                  }}>
                    {ALL_SCENES.map((scene) => {
                      const customUrl = bgCustomImages[scene];
                      return (
                        <div key={scene} style={{
                          border: "1px solid var(--color-border)",
                          borderRadius: "8px",
                          overflow: "hidden",
                          background: "var(--color-bg-secondary)",
                        }}>
                          {/* Preview swatch */}
                          <div style={{
                            height: "60px",
                            background: customUrl
                              ? `url(${customUrl}) center/cover`
                              : SCENE_GRADIENTS[scene],
                          }} />
                          <div style={{ padding: "8px" }}>
                            <div style={{
                              fontSize: "13px",
                              fontFamily: "var(--font-body)",
                              color: "var(--color-text)",
                              marginBottom: "6px",
                              fontWeight: 500,
                            }}>
                              {SCENE_LABELS[scene]}
                            </div>
                            <div style={{ display: "flex", gap: "6px" }}>
                              <label style={{
                                fontSize: "11px",
                                padding: "3px 8px",
                                borderRadius: "4px",
                                border: "1px solid var(--color-border)",
                                background: "var(--color-bg-card)",
                                color: "var(--color-text-secondary)",
                                cursor: "pointer",
                                fontFamily: "var(--font-body)",
                              }}>
                                Upload
                                <input
                                  type="file"
                                  accept="image/jpeg,image/png,image/webp"
                                  style={{ display: "none" }}
                                  onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) handleBgUpload(scene, file);
                                    e.target.value = "";
                                  }}
                                />
                              </label>
                              {customUrl && (
                                <button
                                  style={{
                                    fontSize: "11px",
                                    padding: "3px 8px",
                                    borderRadius: "4px",
                                    border: "1px solid var(--color-border)",
                                    background: "var(--color-bg-card)",
                                    color: "var(--color-danger)",
                                    cursor: "pointer",
                                    fontFamily: "var(--font-body)",
                                  }}
                                  onClick={() => handleBgDelete(scene)}
                                >
                                  Remove
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
      </>)}

      {activeTab === "services" && (<>
      {/* Services section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Services</h3>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("metar_enabled") === true}
              onChange={(e) => updateField("metar_enabled", e.target.checked)}
            />
            Enable METAR data
          </label>
        </div>
        <div style={fieldGroup}>
          <label style={labelStyle}>METAR Station ID</label>
          <input
            style={inputStyle}
            type="text"
            placeholder="e.g. KJFK"
            value={String(val("metar_station") || "")}
            onChange={(e) => updateField("metar_station", e.target.value)}
          />
        </div>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("nws_enabled") === true}
              onChange={(e) => updateField("nws_enabled", e.target.checked)}
            />
            Enable NWS forecast data
          </label>
        </div>
      </div>

      {/* Weather Underground section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Weather Underground</h3>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("wu_enabled") === true}
              onChange={(e) => updateField("wu_enabled", e.target.checked)}
            />
            Enable Weather Underground uploads
          </label>
        </div>
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Station ID</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="e.g. KNCDUNN12"
              value={String(val("wu_station_id") || "")}
              onChange={(e) => updateField("wu_station_id", e.target.value)}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Station Key</label>
            <input
              style={inputStyle}
              type="password"
              placeholder="Your WU station key"
              value={String(val("wu_station_key") || "")}
              onChange={(e) => updateField("wu_station_key", e.target.value)}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Upload Interval</label>
            <select
              style={selectStyle}
              value={String(val("wu_upload_interval") || "60")}
              onChange={(e) => updateField("wu_upload_interval", parseInt(e.target.value))}
            >
              <option value="10">10 seconds</option>
              <option value="15">15 seconds</option>
              <option value="30">30 seconds</option>
              <option value="60">60 seconds</option>
              <option value="120">2 minutes</option>
              <option value="300">5 minutes</option>
            </select>
          </div>
        </div>
      </div>

      {/* CWOP / APRS section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>CWOP / APRS</h3>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("cwop_enabled") === true}
              onChange={(e) => updateField("cwop_enabled", e.target.checked)}
            />
            Enable CWOP uploads
          </label>
        </div>
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Callsign</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="e.g. CW1234 or N0CALL"
              value={String(val("cwop_callsign") || "")}
              onChange={(e) => updateField("cwop_callsign", e.target.value)}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Upload Interval</label>
            <select
              style={selectStyle}
              value={String(val("cwop_upload_interval") || "300")}
              onChange={(e) => updateField("cwop_upload_interval", parseInt(e.target.value))}
            >
              <option value="300">5 minutes</option>
              <option value="600">10 minutes</option>
              <option value="900">15 minutes</option>
            </select>
          </div>
        </div>
      </div>

      {/* Telegram Bot section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Telegram Bot</h3>
        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("bot_telegram_enabled") === true}
              onChange={(e) => updateField("bot_telegram_enabled", e.target.checked)}
            />
            Enable Telegram bot
          </label>
        </div>
        <div style={gridTwoCol(isMobile)}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Bot Token</label>
            <input
              style={inputStyle}
              type="password"
              placeholder="From @BotFather"
              value={String(val("bot_telegram_token") || "")}
              onChange={(e) => updateField("bot_telegram_token", e.target.value)}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>Chat ID</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="Target chat or group ID"
              value={String(val("bot_telegram_chat_id") || "")}
              onChange={(e) => updateField("bot_telegram_chat_id", e.target.value)}
            />
            <span style={{ fontSize: "12px", color: "var(--color-text-muted)", marginTop: "4px", display: "block" }}>
              Comma-separated for multiple chats
            </span>
          </div>
        </div>
        <div style={{ marginBottom: "16px" }}>
          <label style={labelStyle}>Commands</label>
          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
            {["current", "status", "help"].map((cmd) => {
              const cmds = String(val("bot_telegram_commands") || "").split(",").map((s) => s.trim());
              return (
                <label key={cmd} style={checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={cmds.includes(cmd)}
                    onChange={(e) => {
                      const updated = e.target.checked
                        ? [...cmds, cmd]
                        : cmds.filter((c) => c !== cmd);
                      updateField("bot_telegram_commands", updated.filter(Boolean).join(","));
                    }}
                  />
                  /{cmd}
                </label>
              );
            })}
          </div>
        </div>
        <div style={{ marginBottom: "16px" }}>
          <label style={labelStyle}>Notifications</label>
          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap" }}>
            {[["nowcast", "Nowcast updates"], ["alerts", "Alert thresholds"]].map(([key, label]) => {
              const notifs = String(val("bot_telegram_notifications") || "").split(",").map((s) => s.trim());
              return (
                <label key={key} style={checkboxLabel}>
                  <input
                    type="checkbox"
                    checked={notifs.includes(key)}
                    onChange={(e) => {
                      const updated = e.target.checked
                        ? [...notifs, key]
                        : notifs.filter((n) => n !== key);
                      updateField("bot_telegram_notifications", updated.filter(Boolean).join(","));
                    }}
                  />
                  {label}
                </label>
              );
            })}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          <button
            style={{ ...btnPrimary, opacity: telegramTesting ? 0.6 : 1 }}
            disabled={telegramTesting || !val("bot_telegram_token") || !val("bot_telegram_chat_id")}
            onClick={async () => {
              setTelegramTesting(true);
              setTelegramTestResult(null);
              try {
                const resp = await fetch(`${API_BASE}/api/telegram/test`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    token: String(val("bot_telegram_token") || ""),
                    chat_id: String(val("bot_telegram_chat_id") || "").split(",")[0].trim(),
                  }),
                });
                if (resp.ok) {
                  setTelegramTestResult("Test message sent successfully!");
                } else {
                  const data = await resp.json().catch(() => ({ detail: "Unknown error" }));
                  setTelegramTestResult(`Error: ${data.detail || resp.statusText}`);
                }
              } catch (err) {
                setTelegramTestResult(`Error: ${err instanceof Error ? err.message : "Network error"}`);
              } finally {
                setTelegramTesting(false);
              }
            }}
          >
            {telegramTesting ? "Sending..." : "Send Test Message"}
          </button>
          {telegramTestResult && (
            <span style={{
              fontSize: "13px",
              fontFamily: "var(--font-body)",
              color: telegramTestResult.startsWith("Error") ? "var(--color-danger)" : "var(--color-success)",
            }}>
              {telegramTestResult}
            </span>
          )}
        </div>
        {val("bot_telegram_last_error") && (
          <div style={{
            marginTop: "12px",
            padding: "8px 12px",
            borderRadius: "6px",
            fontSize: "13px",
            fontFamily: "var(--font-body)",
            background: "rgba(211,47,47,0.1)",
            border: "1px solid var(--color-danger)",
            color: "var(--color-danger)",
          }}>
            Last error: {String(val("bot_telegram_last_error"))}
          </div>
        )}
      </div>
      </>)}

      {activeTab === "alerts" && (<>
      {/* ==================== Alerts ==================== */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Alerts</h3>

        {alertThresholds.length > 0 && (
          <div style={{ marginBottom: "12px" }}>
            {alertThresholds.map((t, idx) => (
              <div
                key={t.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: isMobile ? "8px" : "12px",
                  padding: "8px 0",
                  borderBottom: idx < alertThresholds.length - 1 ? "1px solid var(--color-border)" : "none",
                  flexWrap: isMobile ? "wrap" : "nowrap",
                }}
              >
                <input
                  type="checkbox"
                  checked={t.enabled}
                  onChange={() => {
                    const updated = [...alertThresholds];
                    updated[idx] = { ...t, enabled: !t.enabled };
                    setAlertThresholds(updated);
                    setAlertSuccess(false);
                  }}
                />
                <span style={{ flex: 1, minWidth: 0, fontSize: isMobile ? "13px" : "14px", fontFamily: "var(--font-body)", color: t.enabled ? "var(--color-text)" : "var(--color-text-muted)" }}>
                  <strong>{t.label}</strong> — {t.sensor} {t.operator} {t.value}
                </span>
                <span style={{ fontSize: "12px", color: "var(--color-text-muted)", whiteSpace: "nowrap" }}>
                  {t.cooldown_min}m cooldown
                </span>
                <button
                  onClick={() => {
                    setAlertThresholds(alertThresholds.filter((_, i) => i !== idx));
                    setAlertSuccess(false);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--color-danger)",
                    cursor: "pointer",
                    fontSize: "16px",
                    padding: "4px 8px",
                    flexShrink: 0,
                  }}
                  title="Delete"
                >
                  &#x2715;
                </button>
              </div>
            ))}
          </div>
        )}

        {alertThresholds.length === 0 && !showAddAlert && (
          <p style={{ fontSize: "14px", color: "var(--color-text-muted)", marginBottom: "12px", fontFamily: "var(--font-body)" }}>
            No alerts configured. Add one to get notified when conditions exceed a threshold.
          </p>
        )}

        {showAddAlert && (
          <div style={{ ...cardStyle, background: "var(--color-bg-secondary)", marginBottom: "12px", padding: isMobile ? "12px" : "20px" }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "1fr 1fr" : "180px 160px 70px 90px 80px",
              gap: isMobile ? "10px" : "12px",
              alignItems: "end",
            }}>
              <div style={isMobile ? { gridColumn: "1 / -1" } : undefined}>
                <label style={labelStyle}>Label</label>
                <input
                  style={inputStyle}
                  placeholder="e.g. Freeze Warning"
                  value={newAlert.label ?? ""}
                  onChange={(e) => setNewAlert({ ...newAlert, label: e.target.value })}
                />
              </div>
              <div style={isMobile ? { gridColumn: "1 / -1" } : undefined}>
                <label style={labelStyle}>Sensor</label>
                <select
                  style={selectStyle}
                  value={newAlert.sensor ?? "outside_temp"}
                  onChange={(e) => setNewAlert({ ...newAlert, sensor: e.target.value })}
                >
                  <option value="outside_temp">Outside Temp</option>
                  <option value="inside_temp">Inside Temp</option>
                  <option value="wind_speed">Wind Speed</option>
                  <option value="barometer">Barometer</option>
                  <option value="outside_humidity">Humidity</option>
                  <option value="rain_rate">Rain Rate</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>Condition</label>
                <select
                  style={selectStyle}
                  value={newAlert.operator ?? "<="}
                  onChange={(e) => setNewAlert({ ...newAlert, operator: e.target.value as AlertThreshold["operator"] })}
                >
                  <option value=">=">&#8805;</option>
                  <option value="<=">&#8804;</option>
                  <option value=">">&gt;</option>
                  <option value="<">&lt;</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>Value</label>
                <input
                  type="number"
                  style={inputStyle}
                  value={newAlert.value ?? 0}
                  onChange={(e) => setNewAlert({ ...newAlert, value: parseFloat(e.target.value) || 0 })}
                />
              </div>
              <div style={isMobile ? { gridColumn: "1 / -1" } : undefined}>
                <label style={labelStyle}>Cooldown (min)</label>
                <input
                  type="number"
                  style={inputStyle}
                  value={newAlert.cooldown_min ?? 15}
                  onChange={(e) => setNewAlert({ ...newAlert, cooldown_min: parseInt(e.target.value) || 15 })}
                />
              </div>
            </div>

            <div style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
              <button
                style={btnPrimary}
                onClick={() => {
                  if (!newAlert.label?.trim()) return;
                  const id = `alert-${Date.now()}`;
                  setAlertThresholds([...alertThresholds, {
                    id,
                    sensor: newAlert.sensor ?? "outside_temp",
                    operator: (newAlert.operator ?? "<=") as AlertThreshold["operator"],
                    value: newAlert.value ?? 0,
                    label: newAlert.label?.trim() ?? "",
                    enabled: true,
                    cooldown_min: newAlert.cooldown_min ?? 15,
                  }]);
                  setShowAddAlert(false);
                  setNewAlert({ sensor: "outside_temp", operator: "<=", value: 32, label: "", cooldown_min: 15, enabled: true });
                  setAlertSuccess(false);
                }}
              >
                Add
              </button>
              <button
                style={{ ...btnPrimary, background: "var(--color-bg-secondary)", color: "var(--color-text)", border: "1px solid var(--color-border)" }}
                onClick={() => setShowAddAlert(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          {!showAddAlert && (
            <button style={btnPrimary} onClick={() => setShowAddAlert(true)}>
              Add Alert
            </button>
          )}
          <button
            style={{
              ...btnPrimary,
              opacity: alertSaving ? 0.6 : 1,
            }}
            onClick={async () => {
              setAlertSaving(true);
              setAlertSuccess(false);
              try {
                await updateConfig([{ key: "alert_thresholds", value: JSON.stringify(alertThresholds) }]);
                setAlertSuccess(true);
              } catch {
                setError("Failed to save alerts");
              } finally {
                setAlertSaving(false);
              }
            }}
            disabled={alertSaving}
          >
            {alertSaving ? "Saving..." : "Save Alerts"}
          </button>

          {alertSuccess && (
            <span style={{ color: "var(--color-success)", fontSize: "14px", fontFamily: "var(--font-body)" }}>
              Alerts saved.
            </span>
          )}
        </div>
      </div>
      </>)}

      {activeTab === "nowcast" && (<>
      {/* AI Nowcast section */}
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>AI Nowcast</h3>

        {/* Mode selector + Remote URL — always visible */}
        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
          gap: isMobile ? "12px" : "16px",
          marginBottom: "16px",
          alignItems: "end",
        }}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Nowcast Mode</label>
            <select
              style={selectStyle}
              value={String(val("nowcast_mode") || "local")}
              onChange={(e) => updateField("nowcast_mode", e.target.value)}
            >
              <option value="local">Local (kanfei-nowcast installed)</option>
              <option value="remote">Remote (external endpoint)</option>
            </select>
          </div>
          {String(val("nowcast_mode") || "local") === "remote" && (
            <div style={fieldGroup}>
              <label style={labelStyle}>
                Remote Endpoint URL
                <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                  kanfei-nowcast server address
                </span>
              </label>
              <input
                style={{ ...inputStyle }}
                type="text"
                placeholder="http://192.168.1.100:8100"
                value={String(val("nowcast_remote_url") || "")}
                onChange={(e) => updateField("nowcast_remote_url", e.target.value)}
              />
            </div>
          )}
        </div>

        {/* Remote mode — endpoint URL, API key, preset, and info */}
        {String(val("nowcast_mode") || "local") === "remote" && (<>
          <div style={fieldGroup}>
            <label style={labelStyle}>
              API Key
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                Provided with your kanfei-nowcast subscription
              </span>
            </label>
            <input
              style={{ ...inputStyle, maxWidth: "480px" }}
              type="password"
              placeholder="knc_live_..."
              value={String(val("nowcast_remote_api_key") || "")}
              onChange={(e) => updateField("nowcast_remote_api_key", e.target.value)}
            />
          </div>
          <div style={fieldGroup}>
            <label style={labelStyle}>
              Quality Preset
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                Controls which AI model is used. During severe weather, the system automatically
                uses the best available model regardless of this setting.
              </span>
            </label>
            <select
              style={{ ...selectStyle, maxWidth: "480px" }}
              value={String(val("nowcast_quality_preset") || "economy")}
              onChange={(e) => updateField("nowcast_quality_preset", e.target.value)}
            >
              {presetOptions.length > 0
                ? presetOptions.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} — {p.description}</option>
                  ))
                : <>
                    <option value="economy">Economy — lowest cost, Haiku for routine, Sonnet for severe</option>
                    <option value="standard">Standard — Haiku for routine, Opus for warnings</option>
                    <option value="premium">Premium — Sonnet always, Opus for severe weather</option>
                  </>
              }
            </select>
          </div>
          <p style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", margin: "0", lineHeight: 1.5 }}>
            Data sources, radar, and nearby stations are configured on the remote server.
            The quality preset and update interval are the only engine settings managed here.
          </p>
        </>)}

        {/* Local mode — full engine configuration */}
        {String(val("nowcast_mode") || "local") !== "remote" && (<>
        <p style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", margin: "0 0 16px 0", lineHeight: 1.5 }}>
          Requires the kanfei-nowcast package. NWS alerts, forecast integration, NEXRAD radar, and nearby
          ASOS/AWOS stations require a US location. International stations can still use the base nowcast
          with local sensor data and CWOP/APRS-IS neighbors.
        </p>

        {/* API Key */}
        <div style={fieldGroup}>
          <label style={labelStyle}>
            Anthropic API Key
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
              Or set ANTHROPIC_API_KEY environment variable
            </span>
          </label>
          <input
            style={{ ...inputStyle, maxWidth: "480px" }}
            type="password"
            placeholder="sk-ant-..."
            value={String(val("nowcast_api_key") || "")}
            onChange={(e) => updateField("nowcast_api_key", e.target.value)}
          />
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>
            Quality Preset
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
              Controls which AI model is used for routine weather. During severe weather,
              the system automatically escalates to the best available model.
            </span>
          </label>
          <select
            style={{ ...selectStyle, maxWidth: "480px" }}
            value={String(val("nowcast_quality_preset") || "economy")}
            onChange={(e) => updateField("nowcast_quality_preset", e.target.value)}
          >
            {presetOptions.length > 0
              ? presetOptions.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} — {p.description}</option>
                ))
              : <>
                  <option value="economy">Economy — Haiku for routine, Sonnet for severe</option>
                  <option value="standard">Standard — Haiku for routine, Opus for warnings</option>
                  <option value="premium">Premium — Sonnet always, Opus for severe weather</option>
                </>
            }
          </select>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
          gap: isMobile ? "12px" : "16px",
        }}>
          <div style={fieldGroup}>
            <label style={labelStyle}>Update Interval</label>
            <select
              style={selectStyle}
              value={String(val("nowcast_interval") || "900")}
              onChange={(e) => updateField("nowcast_interval", parseInt(e.target.value))}
            >
              <option value="300">5 minutes</option>
              <option value="600">10 minutes</option>
              <option value="900">15 minutes</option>
              <option value="1800">30 minutes</option>
              <option value="3600">1 hour</option>
            </select>
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("nowcast_radar_enabled") !== false}
              onChange={(e) => updateField("nowcast_radar_enabled", e.target.checked)}
            />
            Include NEXRAD radar imagery
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px" }}>
              Sends radar image to Claude for precipitation analysis (~250 extra tokens/call)
            </span>
          </label>
        </div>

        {/* Nearby Stations sub-section */}
        <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "16px", marginTop: "8px", marginBottom: "16px" }}>
          <div style={{ fontSize: "15px", fontFamily: "var(--font-heading)", color: "var(--color-text)", marginBottom: "8px" }}>
            Nearby Stations
          </div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginBottom: "12px" }}>
            Adds observations from nearby weather stations so the AI can detect approaching weather patterns and spatial differences.
          </div>

          <div style={fieldGroup}>
            <label style={checkboxLabel}>
              <input
                type="checkbox"
                checked={val("nowcast_nearby_iem_enabled") !== false}
                onChange={(e) => updateField("nowcast_nearby_iem_enabled", e.target.checked)}
              />
              ASOS/AWOS stations (IEM Mesonet)
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px" }}>
                Official NWS airport stations — free, no API key needed
              </span>
            </label>
          </div>

          <div style={fieldGroup}>
            <label style={checkboxLabel}>
              <input
                type="checkbox"
                checked={val("nowcast_nearby_wu_enabled") === true}
                onChange={(e) => updateField("nowcast_nearby_wu_enabled", e.target.checked)}
              />
              Weather Underground PWS
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px" }}>
                Personal weather stations — requires WU API key
              </span>
            </label>
          </div>

          <div style={fieldGroup}>
            <label style={checkboxLabel}>
              <input
                type="checkbox"
                checked={val("nowcast_nearby_aprs_enabled") === true}
                onChange={(e) => updateField("nowcast_nearby_aprs_enabled", e.target.checked)}
              />
              CWOP / APRS-IS stations
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px" }}>
                Citizen weather stations via APRS-IS — free, no API key needed
              </span>
            </label>
          </div>

          {val("nowcast_nearby_wu_enabled") === true && (
            <div style={{ ...fieldGroup, marginLeft: "24px" }}>
              <label style={labelStyle}>WU API Key</label>
              <input
                style={{ ...inputStyle, maxWidth: "480px" }}
                type="password"
                placeholder="Your Weather Underground API key"
                value={String(val("nowcast_wu_api_key") || "")}
                onChange={(e) => updateField("nowcast_wu_api_key", e.target.value)}
              />
            </div>
          )}

          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
            gap: isMobile ? "12px" : "16px",
          }}>
            {val("nowcast_nearby_iem_enabled") !== false && (
              <div style={fieldGroup}>
                <label style={labelStyle}>Max ASOS Stations</label>
                <select
                  style={selectStyle}
                  value={String(val("nowcast_nearby_max_iem") || "5")}
                  onChange={(e) => updateField("nowcast_nearby_max_iem", parseInt(e.target.value))}
                >
                  <option value="3">3</option>
                  <option value="5">5</option>
                  <option value="8">8</option>
                  <option value="10">10</option>
                </select>
              </div>
            )}
            {val("nowcast_nearby_wu_enabled") === true && (
              <div style={fieldGroup}>
                <label style={labelStyle}>Max WU Stations</label>
                <select
                  style={selectStyle}
                  value={String(val("nowcast_nearby_max_wu") || "5")}
                  onChange={(e) => updateField("nowcast_nearby_max_wu", parseInt(e.target.value))}
                >
                  <option value="3">3</option>
                  <option value="5">5</option>
                  <option value="8">8</option>
                  <option value="10">10</option>
                </select>
              </div>
            )}
            {val("nowcast_nearby_aprs_enabled") === true && (
              <div style={fieldGroup}>
                <label style={labelStyle}>Max APRS Stations</label>
                <select
                  style={selectStyle}
                  value={String(val("nowcast_nearby_max_aprs") || "10")}
                  onChange={(e) => updateField("nowcast_nearby_max_aprs", parseInt(e.target.value))}
                >
                  <option value="5">5</option>
                  <option value="10">10</option>
                  <option value="15">15</option>
                  <option value="20">20</option>
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Fallback Providers (local mode only) */}
        <div style={{ borderTop: "1px solid var(--color-border)", paddingTop: "16px", marginTop: "16px", marginBottom: "16px" }}>
          <div style={{ fontSize: "15px", fontFamily: "var(--font-heading)", color: "var(--color-text)", marginBottom: "4px" }}>
            Fallback Providers
          </div>
          <div style={{ fontSize: "12px", color: "var(--color-text-muted)", fontFamily: "var(--font-body)", marginBottom: "12px" }}>
            When Claude is unavailable (overloaded, rate limited), automatically retry with an alternative provider.
            All providers share conversation history and receive radar imagery.
          </div>

          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
            gap: isMobile ? "12px" : "16px",
          }}>
            {/* Grok column */}
            <div>
              <div style={fieldGroup}>
                <label style={labelStyle}>
                  Grok (xAI) API Key
                  <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                    Or set XAI_API_KEY environment variable
                  </span>
                </label>
                <input
                  style={inputStyle}
                  type="password"
                  placeholder="xai-..."
                  value={String(val("nowcast_fallback_grok_api_key") || "")}
                  onChange={(e) => updateField("nowcast_fallback_grok_api_key", e.target.value)}
                />
              </div>
              {val("nowcast_fallback_grok_api_key") && (
                <div style={fieldGroup}>
                  <label style={labelStyle}>Grok Model</label>
                  <select
                    style={selectStyle}
                    value={String(val("nowcast_fallback_grok_model") || "grok-3-mini")}
                    onChange={(e) => updateField("nowcast_fallback_grok_model", e.target.value)}
                  >
                    <option value="grok-4-1-fast-reasoning">Grok 4.1 Fast (vision + reasoning)</option>
                    <option value="grok-3">Grok 3</option>
                    <option value="grok-3-mini">Grok 3 Mini (fastest)</option>
                    <option value="grok-2">Grok 2 (previous gen)</option>
                  </select>
                </div>
              )}
            </div>

            {/* OpenAI column */}
            <div>
              <div style={fieldGroup}>
                <label style={labelStyle}>
                  OpenAI API Key
                  <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                    Or set OPENAI_API_KEY environment variable
                  </span>
                </label>
                <input
                  style={inputStyle}
                  type="password"
                  placeholder="sk-..."
                  value={String(val("nowcast_fallback_openai_api_key") || "")}
                  onChange={(e) => updateField("nowcast_fallback_openai_api_key", e.target.value)}
                />
              </div>
              {val("nowcast_fallback_openai_api_key") && (
                <div style={fieldGroup}>
                  <label style={labelStyle}>OpenAI Model</label>
                  <select
                    style={selectStyle}
                    value={String(val("nowcast_fallback_openai_model") || "gpt-4o-mini")}
                    onChange={(e) => updateField("nowcast_fallback_openai_model", e.target.value)}
                  >
                    <option value="gpt-4o">GPT-4o (best overall)</option>
                    <option value="gpt-4o-mini">GPT-4o Mini (fastest)</option>
                    <option value="o3-mini">o3-mini (reasoning)</option>
                  </select>
                </div>
              )}
            </div>
          </div>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
          gap: isMobile ? "12px" : "16px",
        }}>

          <div style={fieldGroup}>
            <label style={labelStyle}>Forecast Horizon</label>
            <select
              style={selectStyle}
              value={String(val("nowcast_horizon") || "2")}
              onChange={(e) => updateField("nowcast_horizon", parseInt(e.target.value))}
            >
              <option value="2">2 hours</option>
              <option value="4">4 hours</option>
              <option value="6">6 hours</option>
              <option value="8">8 hours</option>
              <option value="12">12 hours</option>
            </select>
          </div>

          <div style={fieldGroup}>
            <label style={labelStyle}>
              Max Output Tokens
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                Increase if responses get truncated
              </span>
            </label>
            <select
              style={selectStyle}
              value={String(val("nowcast_max_tokens") || "3500")}
              onChange={(e) => updateField("nowcast_max_tokens", parseInt(e.target.value))}
            >
              <option value="1500">1500</option>
              <option value="2000">2000</option>
              <option value="2500">2500</option>
              <option value="3000">3000</option>
              <option value="3500">3500</option>
              <option value="4000">4000</option>
              <option value="4500">4500</option>
              <option value="5000">5000</option>
              <option value="6000">6000</option>
              <option value="8000">8000</option>
            </select>
          </div>

          <div style={fieldGroup}>
            <label style={labelStyle}>Nearby Station Radius (miles)</label>
            <input
              style={inputStyle}
              type="number"
              min="5"
              max="100"
              step="5"
              value={String(val("nowcast_radius") || "25")}
              onChange={(e) => updateField("nowcast_radius", parseInt(e.target.value) || 25)}
            />
          </div>

          <div style={fieldGroup}>
            <label style={labelStyle}>
              Knowledge Auto-Accept (hours)
              <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px" }}>
                0 = manual approval only
              </span>
            </label>
            <input
              style={inputStyle}
              type="number"
              min="0"
              max="720"
              step="1"
              value={val("nowcast_knowledge_auto_accept_hours") !== "" ? String(val("nowcast_knowledge_auto_accept_hours")) : "48"}
              onChange={(e) => updateField("nowcast_knowledge_auto_accept_hours", parseInt(e.target.value) || 0)}
            />
          </div>
        </div>
        </>)}{/* end local mode settings */}
      </div>
      </>)}

      {activeTab === "spray" && (<>
      <div style={{ ...cardStyle, padding: isMobile ? "12px" : "20px" }}>
        <h3 style={sectionTitle}>Spray Advisor</h3>

        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={val("spray_ai_enabled") === true}
              onChange={(e) => updateField("spray_ai_enabled", e.target.checked)}
            />
            Enable AI-enhanced spray recommendations
            <span style={{ fontSize: "11px", color: "var(--color-text-muted)", display: "block", marginTop: "2px", marginLeft: "24px" }}>
              Uses the Nowcast AI to provide detailed commentary on spray windows, beyond rule-based go/no-go checks.
              Requires AI Nowcast to be enabled with a valid API key.
            </span>
          </label>
        </div>
      </div>
      </>)}

      {activeTab === "usage" && (<UsageTab
        config={configItems}
        val={val}
        updateField={updateField}
        isMobile={isMobile}
        cardStyle={cardStyle}
        sectionTitle={sectionTitle}
        labelStyle={labelStyle}
        inputStyle={inputStyle}
        fieldGroup={fieldGroup}
      />)}

      {activeTab === "database" && (<DatabaseTab isMobile={isMobile} />)}

      {activeTab === "backup" && (<BackupTab val={val} updateField={updateField} isMobile={isMobile} />)}

      {activeTab === "system" && (<SystemTab isMobile={isMobile} />)}

      </div>{/* end padding wrapper */}
      </div>{/* end scrollable */}
    </div>
  );
}

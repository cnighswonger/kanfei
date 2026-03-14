// ============================================================
// HTTP API client for the Davis Weather Station backend.
// Pure fetch-based -- no external dependencies.
// ============================================================

import type { ConfigItem } from "./types.ts";
import type {
  CurrentConditions,
  HistoryResponse,
  ForecastResponse,
  AstronomyResponse,
  StationStatus,
} from "./types.ts";
import { API_BASE } from "../utils/constants.ts";

// --- Helpers ---

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, init);

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new ApiError(
      response.status,
      `API ${response.status}: ${body || response.statusText}`,
    );
  }

  return (await response.json()) as T;
}

// --- Public API functions ---

export function fetchCurrentConditions(): Promise<CurrentConditions> {
  return request<CurrentConditions>("/api/current");
}

export function fetchHistory(
  sensor: string,
  start: string,
  end: string,
  resolution: string = "5m",
): Promise<HistoryResponse> {
  const params = new URLSearchParams({ sensor, start, end, resolution });
  return request<HistoryResponse>(`/api/history?${params.toString()}`);
}

export function fetchForecast(): Promise<ForecastResponse> {
  return request<ForecastResponse>("/api/forecast");
}

export function fetchAstronomy(): Promise<AstronomyResponse> {
  return request<AstronomyResponse>("/api/astronomy");
}

export function fetchStationStatus(): Promise<StationStatus> {
  return request<StationStatus>("/api/station");
}

export function fetchConfig(): Promise<ConfigItem[]> {
  return request<ConfigItem[]>("/api/config");
}

export function updateConfig(items: ConfigItem[]): Promise<ConfigItem[]> {
  return request<ConfigItem[]>("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(items),
  });
}

export function syncStationTime(): Promise<{ status: string; synced_to?: string; message?: string }> {
  return request("/api/station/sync-time", { method: "POST" });
}

// --- Setup ---

import type {
  SetupStatus,
  SerialPortList,
  ProbeResult,
  AutoDetectResult,
  SetupConfig,
  ReconnectResult,
} from "./types.ts";

export function fetchSetupStatus(): Promise<SetupStatus> {
  return request<SetupStatus>("/api/setup/status");
}

export function fetchSerialPorts(): Promise<SerialPortList> {
  return request<SerialPortList>("/api/setup/serial-ports");
}

export function probeSerialPort(
  port: string,
  baudRate: number,
): Promise<ProbeResult> {
  return request<ProbeResult>("/api/setup/probe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ port, baud_rate: baudRate }),
  });
}

export function autoDetectStation(): Promise<AutoDetectResult> {
  return request<AutoDetectResult>("/api/setup/auto-detect", {
    method: "POST",
  });
}

export function completeSetup(
  config: SetupConfig,
): Promise<{ status: string; reconnect: ReconnectResult }> {
  return request("/api/setup/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export function reconnectStation(): Promise<ReconnectResult> {
  return request<ReconnectResult>("/api/setup/reconnect", {
    method: "POST",
  });
}

// --- WeatherLink Hardware Config ---

import type {
  WeatherLinkConfig,
  WeatherLinkConfigUpdate,
} from "./types.ts";

export function fetchWeatherLinkConfig(): Promise<WeatherLinkConfig> {
  return request<WeatherLinkConfig>("/api/weatherlink/config");
}

export function updateWeatherLinkConfig(
  config: WeatherLinkConfigUpdate,
): Promise<{ results: Record<string, string>; config: WeatherLinkConfig }> {
  return request("/api/weatherlink/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export function clearRainDaily(): Promise<{ success: boolean }> {
  return request("/api/weatherlink/clear-rain-daily", { method: "POST" });
}

export function clearRainYearly(): Promise<{ success: boolean }> {
  return request("/api/weatherlink/clear-rain-yearly", { method: "POST" });
}

export function forceArchive(): Promise<{ success: boolean }> {
  return request("/api/weatherlink/force-archive", { method: "POST" });
}

// --- Nowcast ---

import type { NowcastData, NowcastKnowledgeEntry, NowcastVerification, NWSActiveAlertsResponse } from "./types.ts";
import type { SprayProduct, SpraySchedule, SprayEvaluation, SprayConditions, SprayOutcome, SprayProductStats } from "./types.ts";

export function fetchNowcast(): Promise<NowcastData | null> {
  return request<NowcastData | null>("/api/nowcast");
}

export interface NowcastStatus {
  active: boolean;
  enabled?: boolean;
  has_data?: boolean;
  error: string | null;
}

export function fetchNowcastStatus(): Promise<NowcastStatus> {
  return request<NowcastStatus>("/api/nowcast/status");
}

export function fetchNowcastHistory(
  limit: number = 20,
): Promise<NowcastData[]> {
  return request<NowcastData[]>(`/api/nowcast/history?limit=${limit}`);
}

export function fetchNowcastKnowledge(
  status?: string,
): Promise<NowcastKnowledgeEntry[]> {
  const params = status ? `?status=${status}` : "";
  return request<NowcastKnowledgeEntry[]>(`/api/nowcast/knowledge${params}`);
}

export function updateNowcastKnowledge(
  id: number,
  status: "accepted" | "rejected",
): Promise<NowcastKnowledgeEntry> {
  return request<NowcastKnowledgeEntry>(`/api/nowcast/knowledge/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function fetchNowcastVerifications(
  limit: number = 20,
): Promise<NowcastVerification[]> {
  return request<NowcastVerification[]>(`/api/nowcast/verifications?limit=${limit}`);
}

export function generateNowcast(): Promise<NowcastData> {
  return request<NowcastData>("/api/nowcast/generate", { method: "POST" });
}

export function fetchNWSAlerts(): Promise<NWSActiveAlertsResponse> {
  return request<NWSActiveAlertsResponse>("/api/nowcast/alerts");
}

// --- Spray Advisor ---

export function fetchSprayProducts(): Promise<SprayProduct[]> {
  return request<SprayProduct[]>("/api/spray/products");
}

export function createSprayProduct(
  product: Omit<SprayProduct, "id" | "is_preset" | "created_at" | "updated_at">,
): Promise<SprayProduct> {
  return request<SprayProduct>("/api/spray/products", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(product),
  });
}

export function updateSprayProduct(
  id: number,
  product: Partial<SprayProduct>,
): Promise<SprayProduct> {
  return request<SprayProduct>(`/api/spray/products/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(product),
  });
}

export function deleteSprayProduct(id: number): Promise<void> {
  return request<void>(`/api/spray/products/${id}`, { method: "DELETE" });
}

export function resetSprayPresets(): Promise<SprayProduct[]> {
  return request<SprayProduct[]>("/api/spray/products/reset-presets", {
    method: "POST",
  });
}

export function fetchSpraySchedules(): Promise<SpraySchedule[]> {
  return request<SpraySchedule[]>("/api/spray/schedules");
}

export function createSpraySchedule(
  schedule: { product_id: number; planned_date: string; planned_start: string; planned_end: string; notes?: string },
): Promise<SpraySchedule> {
  return request<SpraySchedule>("/api/spray/schedules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(schedule),
  });
}

export function deleteSpraySchedule(id: number): Promise<void> {
  return request<void>(`/api/spray/schedules/${id}`, { method: "DELETE" });
}

export function updateSprayScheduleStatus(
  id: number,
  status: "completed" | "cancelled" | "pending",
): Promise<SpraySchedule> {
  return request<SpraySchedule>(`/api/spray/schedules/${id}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function evaluateSpraySchedule(id: number): Promise<SprayEvaluation> {
  return request<SprayEvaluation>(`/api/spray/schedules/${id}/evaluate`, {
    method: "POST",
  });
}

export function quickCheckSpray(productId: number): Promise<SprayEvaluation> {
  return request<SprayEvaluation>("/api/spray/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ product_id: productId }),
  });
}

export function fetchSprayConditions(): Promise<SprayConditions> {
  return request<SprayConditions>("/api/spray/conditions");
}

export function createSprayOutcome(
  scheduleId: number,
  outcome: {
    effectiveness: number;
    actual_rain_hours?: number | null;
    actual_wind_mph?: number | null;
    actual_temp_f?: number | null;
    drift_observed?: boolean;
    product_efficacy?: string | null;
    notes?: string | null;
  },
): Promise<SprayOutcome> {
  return request<SprayOutcome>(`/api/spray/schedules/${scheduleId}/outcome`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(outcome),
  });
}

export function fetchSprayOutcomes(limit = 20): Promise<SprayOutcome[]> {
  return request<SprayOutcome[]>(`/api/spray/outcomes?limit=${limit}`);
}

export function fetchProductOutcomes(productId: number): Promise<SprayOutcome[]> {
  return request<SprayOutcome[]>(`/api/spray/products/${productId}/outcomes`);
}

export function fetchProductStats(productId: number): Promise<SprayProductStats> {
  return request<SprayProductStats>(`/api/spray/products/${productId}/stats`);
}

// --- Usage & Cost Tracking ---

import type { LocalUsageResponse, UsageStatus } from "./types.ts";

export function fetchLocalUsage(): Promise<LocalUsageResponse> {
  return request<LocalUsageResponse>("/api/usage/local");
}

export function fetchUsageStatus(): Promise<UsageStatus> {
  return request<UsageStatus>("/api/usage/status");
}

export function fetchAnthropicUsage(period: string = "7d"): Promise<unknown> {
  return request(`/api/usage/anthropic?period=${period}`);
}

export function fetchAnthropicCost(period: string = "30d"): Promise<unknown> {
  return request(`/api/usage/anthropic/cost?period=${period}`);
}

// --- Database Admin ---

import type { DbStats, PurgeResult, CompactResult } from "./types.ts";

export function fetchDbStats(): Promise<DbStats> {
  return request<DbStats>("/api/db-admin/stats");
}

export function purgeTable(
  table: string,
  opts: { confirm?: string; before?: string },
): Promise<PurgeResult> {
  return request<PurgeResult>(`/api/db-admin/purge/${table}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(opts),
  });
}

export function purgeAll(confirm: string): Promise<Record<string, number>> {
  return request<Record<string, number>>("/api/db-admin/purge-all", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm }),
  });
}

export function compactReadings(
  before: string,
  confirm: string,
): Promise<CompactResult> {
  return request<CompactResult>("/api/db-admin/compact", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ before, confirm }),
  });
}

export function getDbBackupUrl(): string {
  return `${API_BASE}/api/db-admin/export/backup`;
}

export function getDbExportUrl(table: string): string {
  return `${API_BASE}/api/db-admin/export/json/${table}`;
}

// --- System Logs ---

export function fetchLogs(
  level: string = "WARNING",
  limit: number = 200,
): Promise<import("./types.ts").LogEntry[]> {
  return request(`/api/logs?level=${encodeURIComponent(level)}&limit=${limit}`);
}

export { ApiError };

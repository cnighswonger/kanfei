// ============================================================
// TypeScript interfaces matching the Davis Weather Station
// backend Pydantic models.
// ============================================================

// --- Primitives ---

export interface ValueWithUnit {
  value: number;
  unit: string;
}

// --- Current Conditions ---

export interface TemperatureData {
  inside: ValueWithUnit | null;
  outside: ValueWithUnit | null;
}

export interface HumidityData {
  inside: ValueWithUnit | null;
  outside: ValueWithUnit | null;
}

export interface WindData {
  speed: ValueWithUnit | null;
  direction: ValueWithUnit | null;
  cardinal: string | null;
  gust: ValueWithUnit | null;
}

export interface BarometerData {
  value: number | null;
  unit: string;
  trend: string | null;
  trend_rate: number | null;
}

export interface RainData {
  daily: ValueWithUnit | null;
  yearly: ValueWithUnit | null;
  rate: ValueWithUnit | null;
  yesterday?: ValueWithUnit | null;
}

export interface DerivedData {
  heat_index: ValueWithUnit | null;
  dew_point: ValueWithUnit | null;
  wind_chill: ValueWithUnit | null;
  feels_like: ValueWithUnit | null;
  theta_e: ValueWithUnit | null;
}

export interface DailyExtremes {
  outside_temp_hi: ValueWithUnit | null;
  outside_temp_lo: ValueWithUnit | null;
  inside_temp_hi: ValueWithUnit | null;
  inside_temp_lo: ValueWithUnit | null;
  wind_speed_hi: ValueWithUnit | null;
  barometer_hi: ValueWithUnit | null;
  barometer_lo: ValueWithUnit | null;
  humidity_hi: ValueWithUnit | null;
  humidity_lo: ValueWithUnit | null;
  rain_rate_hi: ValueWithUnit | null;
}

export interface CurrentConditions {
  timestamp: string;
  station_type: string;
  temperature: TemperatureData;
  humidity: HumidityData;
  wind: WindData;
  barometer: BarometerData;
  rain: RainData;
  derived: DerivedData;
  solar_radiation: ValueWithUnit | null;
  uv_index: ValueWithUnit | null;
  daily_extremes: DailyExtremes | null;
}

// --- Forecast ---

export interface LocalForecast {
  source: "zambretti";
  text: string;
  confidence: number;
  trend: string | null;
  updated: string;
}

export interface NWSPeriod {
  name: string;
  temperature: number;
  wind: string;
  precipitation_pct: number;
  text: string;
  icon_url: string | null;
  short_forecast: string | null;
  is_daytime: boolean | null;
}

export interface NWSForecast {
  source: "nws";
  periods: NWSPeriod[];
  updated: string;
}

export interface ForecastResponse {
  local: LocalForecast | null;
  nws: NWSForecast | null;
}

// --- Astronomy ---

export interface TwilightTimes {
  dawn: string;
  dusk: string;
}

export interface SunData {
  sunrise: string;
  sunset: string;
  solar_noon: string;
  day_length: string;
  day_change: string;
  civil_twilight: TwilightTimes;
  nautical_twilight: TwilightTimes;
  astronomical_twilight: TwilightTimes;
}

export interface MoonData {
  phase: string;
  illumination: number;
  next_full: string;
  next_new: string;
}

export interface AstronomyResponse {
  sun: SunData;
  moon: MoonData;
}

// --- Station Status ---

export interface StationStatus {
  type_code: number;
  type_name: string;
  connected: boolean;
  link_revision: string;
  poll_interval: number;
  last_poll: string | null;
  archive_records: number;
  uptime_seconds: number;
  crc_errors: number;
  timeouts: number;
  station_time: string | null;
}

// --- Configuration ---

export interface ConfigItem {
  key: string;
  value: string | number | boolean;
  label?: string;
  description?: string;
}

// --- History ---

export interface HistoryPoint {
  timestamp: string;
  value: number | null;
  min?: number | null;
  max?: number | null;
}

export interface HistorySummary {
  min: number | null;
  max: number | null;
  avg: number | null;
  count: number;
}

export interface HistoryResponse {
  sensor: string;
  start: string;
  end: string;
  resolution: string;
  summary: HistorySummary | null;
  points: HistoryPoint[];
}

// --- Alerts ---

export interface AlertThreshold {
  id: string;
  sensor: string;
  operator: ">=" | "<=" | ">" | "<";
  value: number;
  label: string;
  enabled: boolean;
  cooldown_min: number;
}

export interface AlertEvent {
  id: string;
  label: string;
  sensor: string;
  value: number;
  threshold: number;
  operator: string;
}

// --- Nowcast ---

export interface NowcastElement {
  forecast: string;
  confidence: "HIGH" | "MEDIUM" | "LOW" | string;
  timing?: string;
}

export interface NowcastData {
  id: number;
  created_at: string;
  valid_from: string;
  valid_until: string;
  model_used: string;
  summary: string;
  elements: {
    temperature?: NowcastElement;
    precipitation?: NowcastElement;
    wind?: NowcastElement;
    sky?: NowcastElement;
    special?: string | null;
  };
  farming_impact: string | null;
  current_vs_model: string;
  radar_analysis: string | null;
  spray_advisory: {
    summary: string;
    recommendations: Array<{
      schedule_id: number;
      product_name: string;
      go: boolean;
      detail: string;
    }>;
  } | null;
  severe_weather: {
    threat_level: "WATCH" | "WARNING" | "EMERGENCY";
    primary_threat: string;
    summary: string;
    distance_miles: number | null;
    bearing: string | null;
    estimated_arrival: string | null;
    local_evidence: string[];
    recommended_action: string;
  } | null;
  data_quality: string;
  sources_used: string[];
  input_tokens: number;
  output_tokens: number;
}

export interface NowcastKnowledgeEntry {
  id: number;
  created_at: string;
  source: string;
  category: string;
  content: string;
  status: "pending" | "accepted" | "rejected";
  auto_accept_at: string | null;
  reviewed_at: string | null;
  recommendation: string;
}

export interface NowcastVerification {
  id: number;
  nowcast_id: number;
  verified_at: string;
  element: string;
  predicted: string;
  actual: string;
  accuracy_score: number | null;
  notes: string | null;
}

// --- NWS Active Alerts ---

export interface NWSActiveAlert {
  event: string;
  severity: "Extreme" | "Severe" | "Moderate" | "Minor" | "Unknown";
  certainty: string;
  urgency: string;
  headline: string;
  description: string;
  instruction: string;
  onset: string;
  expires: string;
  sender_name: string;
  alert_id: string;
  message_type: string;
  response: string;
}

export interface NWSActiveAlertsResponse {
  alerts: NWSActiveAlert[];
  count: number;
}

// --- WebSocket Messages ---

export interface WSSensorUpdate {
  type: "sensor_update";
  data: CurrentConditions;
}

export interface WSForecastUpdate {
  type: "forecast_update";
  data: ForecastResponse;
}

export interface WSAlertTriggered {
  type: "alert_triggered";
  data: AlertEvent;
}

export interface WSAlertCleared {
  type: "alert_cleared";
  data: { id: string; label: string };
}

export interface WSNowcastUpdate {
  type: "nowcast_update";
  data: NowcastData;
}

export interface WSNowcastWarning {
  type: "nowcast_warning";
  message: string;
}

export interface WSConnectionStatus {
  type: "connection_status";
  connected: boolean;
}

export interface WSSevereWeatherStatus {
  type: "severe_weather_status";
  data: {
    alert_mode: boolean;
    is_new_alert?: boolean;
    alert_count?: number;
    cycle_interval?: number;
  };
}

export type WSMessage = WSSensorUpdate | WSForecastUpdate | WSNowcastUpdate | WSNowcastWarning | WSConnectionStatus | WSAlertTriggered | WSAlertCleared | WSSevereWeatherStatus;

// --- Spray Advisor ---

export interface SprayProduct {
  id: number;
  name: string;
  category: string;
  is_preset: boolean;
  rain_free_hours: number;
  max_wind_mph: number;
  min_temp_f: number;
  max_temp_f: number;
  min_humidity_pct: number | null;
  max_humidity_pct: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface SpraySchedule {
  id: number;
  product_id: number;
  product_name: string;
  planned_date: string;
  planned_start: string;
  planned_end: string;
  status: "pending" | "go" | "no_go" | "completed" | "cancelled";
  evaluation: SprayEvaluation | null;
  ai_commentary: unknown;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConstraintCheck {
  name: string;
  passed: boolean;
  current_value: string;
  threshold: string;
  detail: string;
}

export interface SprayEvaluation {
  go: boolean;
  constraints: ConstraintCheck[];
  overall_detail: string;
  optimal_window: { start: string; end: string; duration_hours: number } | null;
  confidence: "HIGH" | "MEDIUM" | "LOW";
}

export interface SprayConditions {
  wind_speed_mph: number | null;
  wind_gust_mph: number | null;
  temperature_f: number | null;
  humidity_pct: number | null;
  rain_rate: number | null;
  rain_daily: number | null;
  next_rain_hours: number | null;
  overall_spray_ok: boolean;
}

export interface SprayOutcome {
  id: number;
  schedule_id: number;
  product_name: string;
  logged_at: string;
  effectiveness: number;
  actual_rain_hours: number | null;
  actual_wind_mph: number | null;
  actual_temp_f: number | null;
  drift_observed: boolean;
  product_efficacy: string | null;
  notes: string | null;
  created_at: string;
}

export interface SprayProductStats {
  product_id: number;
  product_name: string;
  total_applications: number;
  avg_effectiveness: number | null;
  success_rate: number | null;
  drift_rate: number | null;
  avg_wind_mph: number | null;
  avg_temp_f: number | null;
  tuned_thresholds: Array<{
    name: string;
    preset_value: number;
    tuned_value: number;
    outcome_count: number;
    annotation: string;
  }>;
}

// --- Usage & Cost Tracking ---

export interface UsagePeriodStats {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
}

export interface LocalUsageResponse {
  today: UsagePeriodStats;
  this_month: UsagePeriodStats;
  all_time: UsagePeriodStats;
  model_breakdown: Array<{ model: string } & UsagePeriodStats>;
}

export interface UsageStatus {
  local: boolean;
  anthropic: boolean;
  budget: {
    limit_usd: number;
    current_usd: number;
    paused: boolean;
    auto_pause: boolean;
  };
}

// --- Database Admin ---

export interface DbTableStats {
  table: string;
  row_count: number;
  oldest: string | null;
  newest: string | null;
}

export interface DbStats {
  tables: DbTableStats[];
  db_size_bytes: number;
}

export interface PurgeResult {
  deleted: number;
  remaining: number;
}

export interface CompactResult {
  original_rows: number;
  compacted_rows: number;
  deleted: number;
}

// --- Setup Wizard ---

export interface SetupStatus {
  setup_complete: boolean;
}

export interface SerialPortList {
  ports: string[];
}

export interface ProbeResult {
  success: boolean;
  station_type: string | null;
  station_code: number | null;
  driver_type: string | null;
  error: string | null;
}

export interface AutoDetectResult {
  found: boolean;
  port: string | null;
  baud_rate: number | null;
  station_type: string | null;
  station_code: number | null;
  driver_type: string | null;
  attempts: Array<{ port: string; baud: number; error?: string }>;
}

export interface SetupConfig {
  serial_port: string;
  baud_rate: number;
  station_driver_type: string;
  latitude: number;
  longitude: number;
  elevation: number;
  temp_unit: string;
  pressure_unit: string;
  wind_unit: string;
  rain_unit: string;
  metar_enabled: boolean;
  metar_station: string;
  nws_enabled: boolean;
}

export interface ReconnectResult {
  success: boolean;
  station_type?: string;
  error?: string;
}

// --- WeatherLink Hardware Config ---

export interface WeatherLinkCalibration {
  inside_temp: number;
  outside_temp: number;
  barometer: number;
  outside_humidity: number;
  rain_cal: number;
}

export interface WeatherLinkConfig {
  archive_period: number | null;
  sample_period: number | null;
  calibration: WeatherLinkCalibration;
}

export interface WeatherLinkConfigUpdate {
  archive_period?: number;
  sample_period?: number;
  calibration?: WeatherLinkCalibration;
}

// --- Backup ---

export interface BackupManifest {
  kanfei_version: string;
  timestamp: string;
  db_file: string;
  db_size_bytes: number;
  row_counts: Record<string, number>;
  backgrounds_included: boolean;
  backgrounds_count: number;
  archive_path: string;
  archive_size_bytes: number;
}

export interface BackupInfo {
  name: string;
  size_bytes: number;
  modified: string;
}

// --- System Logs ---

export interface LogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

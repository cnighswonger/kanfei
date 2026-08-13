// ============================================================
// TypeScript interfaces matching the Davis Weather Station
// backend Pydantic models.
// ============================================================

// --- Primitives ---

export interface ValueWithUnit {
  value: number;
  unit: string;
}

// Daily extremes carry an ISO-8601 UTC timestamp (``Z`` suffix) marking
// when the high/low was first observed today.  ``null`` when no rows
// have hit the column yet (server pre-first-reading).
export interface ExtremeReading {
  value: number;
  unit: string;
  at: string | null;
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
  /** Station-computed; null unless the station has a solar sensor. */
  thsw_index: ValueWithUnit | null;
}

export interface DailyExtremes {
  outside_temp_hi: ExtremeReading | null;
  outside_temp_lo: ExtremeReading | null;
  inside_temp_hi: ExtremeReading | null;
  inside_temp_lo: ExtremeReading | null;
  wind_speed_hi: ExtremeReading | null;
  barometer_hi: ExtremeReading | null;
  barometer_lo: ExtremeReading | null;
  humidity_hi: ExtremeReading | null;
  humidity_lo: ExtremeReading | null;
  inside_humidity_hi: ExtremeReading | null;
  inside_humidity_lo: ExtremeReading | null;
  rain_rate_hi: ExtremeReading | null;
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
  /**
   * WHO UV Index warning band ("Low" | "Moderate" | "High" | "Very High" |
   * "Extreme"). Derived server-side from `uv_index` so consumers don't
   * re-implement the same boundary logic. Null when uv_index is null.
   */
  uv_warning: string | null;
  /**
   * Trapezoid-integrated solar radiation since local midnight, in the
   * operator's preferred unit (see `solar_energy_unit` config). Null on
   * stations without a solar sensor or before the second sample of the
   * day lands.
   */
  solar_energy_daily: ValueWithUnit | null;
  /**
   * Evapotranspiration: running totals over day / calendar month /
   * calendar year, in the operator's `rain_unit` (in or mm). Null on
   * stations that don't compute ET (needs solar + temp/humidity/wind).
   */
  et_daily: ValueWithUnit | null;
  et_monthly: ValueWithUnit | null;
  et_yearly: ValueWithUnit | null;
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
  /**
   * Firmware version string as reported by the station (e.g. "1.90" for
   * a VP2/Vue that supports NVER).  `null` when the station cannot report
   * it — VP1, LinkDriver, or any station that has not yet completed the
   * detection handshake.
   */
  firmware_version: string | null;
  /**
   * Firmware build date as a free-form Davis string (e.g. "Aug 15 2013").
   * `null` when unavailable, same rules as firmware_version.  Kept
   * separately because a Vue reports both, and the date is diagnostic
   * even on VP1 where NVER is absent.
   */
  firmware_date: string | null;
  /**
   * Davis product SKU (4-digit ASCII string, e.g. "6351" for Vantage
   * Vue Wireless with WeatherLink IP).  Populated on Vue / VP2 via the
   * undocumented `IDENT` command at connect; `null` on stations that
   * don't support it or when the response was malformed.  See
   * `reference/vantage_fw433_wire_audit.md` §N1.
   */
  product_sku: string | null;
  poll_interval: number;
  last_poll: string | null;
  archive_records: number;
  uptime_seconds: number;
  crc_errors: number;
  timeouts: number;
  station_time: string | null;
  /**
   * Raw wall-clock fields the console reported at the last read. Paired
   * with `server_epoch_ms_at_read` for the frontend's live-tick display
   * (`StationStatus.tsx`): the client advances these components forward
   * by `Date.now() - server_epoch_ms_at_read` and formats them as-is,
   * without any timezone conversion. `year` is null on stations whose
   * `GETTIME` response doesn't include it. Both fields null on
   * disconnected/degraded responses and on stations that don't support
   * GETTIME at all.
   */
  station_time_components: {
    year: number | null;
    month: number;
    day: number;
    hour: number;
    minute: number;
    second: number;
  } | null;
  server_epoch_ms_at_read: number | null;
  /**
   * Battery status derived from the latest sensor reading's `extra_json`
   * (see #236). `null` on stations that don't report battery info, before
   * the first poll returns, or when the extras couldn't be parsed. When
   * present, `transmitters_low` is an empty list to mean "all OK", so
   * consumers can distinguish "OK" (empty list) from "unknown" (whole
   * field null).
   */
  battery: {
    transmitters_low: number[];
    console_voltage: number | null;
    raw_transmitter_bitmask: number | null;
  } | null;
}

// --- Console rain season ---

export interface RainSeasonState {
  /** Console's yearly-rain-reset month (1-12). */
  month: number;
}

export interface RainSeasonResult {
  success: boolean;
  before: number | null;
  after: number | null;
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
  weatherlink_ip: string;
  weatherlink_port: number;
  ecowitt_ip: string;
  tempest_hub_sn: string;
  ambient_listen_port: number;
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

// --- Barometer calibration (Vantage) ---

/**
 * BARDATA readout.  Every field is nullable because the backend's own
 * dataclass is Optional throughout and the snapshot helper returns null
 * outright when a BARDATA read fails — typing these non-null would be
 * the #250 mistake again, where a lie in the type disabled the one tool
 * that would have caught the crash.
 */
export interface BarometerCalibrationState {
  barometer_inhg: number | null;
  elevation_ft: number | null;
  barcal_inhg: number | null;
  /** Factory sensor constants. Read-only; NOT what BAR= sets. */
  gain: number | null;
  offset: number | null;
}

export interface BarometerSnapshot {
  barometer_inhg: number | null;
  elevation_ft: number | null;
  barcal_inhg: number | null;
}

export interface BarometerCalibrationResult {
  success: boolean;
  before: BarometerSnapshot | null;
  after: BarometerSnapshot | null;
}

export interface MetarReference {
  station_id: string;
  station_name: string;
  distance_miles: number;
  bearing_cardinal: string;
  /** ISO 8601 UTC. Age is computed client-side — a server-computed age
   *  would go stale while the panel sits open. */
  observed_at: string;
  altimeter_thousandths_inhg: number;
  altimeter_inhg: number;
  raw_metar: string;
  report_type: string;
}

// --- Multi-station aggregate for barometer calibration (#298) ---

/** One METAR station's median altimeter over the 2h fetch window.
 *  Distinct from MetarReference (single obs) — this is the aggregate
 *  that the multi-station gate votes on. */
export interface StationMedian {
  station_id: string;
  station_name: string;
  distance_miles: number;
  bearing_cardinal: string;
  n_obs: number;
  median_altimeter_thousandths_inhg: number;
  median_altimeter_inhg: number;
  obs_spread_thousandths_inhg: number;
  newest_observed_at: string;
  /** True when the iterated MAD filter rejected this station.  It
   *  still rides in the array so the panel can render it (struck-out
   *  or greyed) instead of silently disappearing. */
  is_outlier: boolean;
  /** True when at least one observation for this station in the
   *  window carried a `PRESRR` / `PRESFR` remark (FMH-1: rising or
   *  falling by ≥0.06 inHg/hr).  The regional-quiescence gate reads
   *  this across survivors; UIs may want to badge the row too. */
  has_rapid_trend: boolean;
}

/** The console's own barometer aggregate over the last N minutes. */
export interface BarometerConsoleSample {
  median_hpa: number;
  n_samples: number;
  window_minutes: number;
  stdev_hpa: number;
  window_start: string;
  window_end: string;
  /** σ over the retrospective window (see recent_window_hours).
   *  Null when fewer than the backend's MIN_RECENT_SAMPLES readings
   *  are present in the window (freshly-installed station, DB reset,
   *  poller silent).  The panel uses this to add a "recently
   *  unsettled" note to any HOLD diagnostic when σ_recent exceeds
   *  the threshold in `BarometerThresholds`. */
  stdev_hpa_recent: number | null;
  n_samples_recent: number;
  recent_window_hours: number;
}

/** Skip-reason codes, stable string constants matching the backend
 *  SKIP_* symbols in `barometer_aggregation.py`. */
export type BarometerSkipReason =
  | "no_console_samples"
  | "insufficient_console_samples"
  | "no_metar_available"
  | "insufficient_stations"
  | "cross_station_disagreement"
  | "unsettled_console"
  | "unsettled_regional";

/** The write decision + everything the UI needs to render it.
 *  Semantics after #307: `median_of_medians_*` is populated whenever
 *  we have enough survivors + console data, regardless of gate
 *  outcomes.  `should_apply` is the algorithm's autonomous decision;
 *  `hold_override_allowed` is true only when the algorithm HOLDs
 *  specifically on cross-station-spread AND a valid recommended
 *  value exists — the UI may then offer an "Accept anyway" button
 *  that commits to the SAME weighted-median value the algorithm
 *  computed. */
export interface BarometerRecommendation {
  should_apply: boolean;
  skip_reason: BarometerSkipReason | null;
  median_of_medians_thousandths_inhg: number | null;
  median_of_medians_inhg: number | null;
  offset_thousandths_inhg: number | null;
  offset_inhg: number | null;
  hold_override_allowed: boolean;
}

/** Thresholds in effect for this aggregation.  Snapshotted so the UI
 *  never hard-codes them and always shows what the daemon actually used. */
export interface BarometerThresholds {
  min_stations: number;
  cross_station_spread_threshold_hpa: number;
  console_window_minutes: number;
  min_console_samples: number;
  max_station_distance_miles: number;
  station_window_hours: number;
  mad_rejection_multiplier: number;
  mad_min_scale_hpa: number;
  mad_max_iterations: number;
  distance_weight_epsilon_miles: number;
  /** null → all stations in bbox count; N → only the N nearest. */
  station_limit_for_calibration: number | null;
  console_stdev_threshold_hpa: number;
  rapid_trend_station_fraction: number;
  recent_window_hours: number;
  recent_unsettled_stdev_threshold_hpa: number;
}

export interface BarometerAggregate {
  console: BarometerConsoleSample | null;
  per_station_medians: StationMedian[];
  n_stations_considered: number;
  /** After iterated MAD outlier rejection.  n_stations_considered
   *  minus n_stations_used = the count of stations flagged is_outlier. */
  n_stations_used: number;
  cross_station_spread_hpa: number | null;
  recommendation: BarometerRecommendation;
  thresholds: BarometerThresholds;
  reference_radius_miles: number;
}

export interface MetarReferenceResponse {
  references: MetarReference[];
  location_configured: boolean;
  home_lat: number;
  home_lon: number;
  radius_miles: number;
  fetched_at: string;
  /** Multi-station aggregate (#298).  `null` when location is not
   *  configured — the same rule as `references: []` in that case. */
  aggregate: BarometerAggregate | null;
}

// --- Destructive console operations ---

/**
 * What overwriting the yearly rain total would cost.
 *
 * `difference_mm` is the data at risk: rain the console counted that
 * Kanfei has not recorded. Null when either side is unknown — a fresh
 * install has no history, and reporting 0 would imply the console counted
 * the whole total since the last poll.
 */
export interface RainPreflight {
  console_mm: number | null;
  last_stored_mm: number | null;
  last_stored_at: string | null;
  difference_mm: number | null;
  /** False means the driver will refuse rather than risk a 2x error. */
  collector_known: boolean;
}

export interface SetYearlyRainResult {
  success: boolean;
  before_mm: number | null;
  after_mm: number | null;
}

export interface ArchivePreflight {
  records_in_kanfei: number;
  latest_synced_at: string | null;
}

// --- Console highs and lows (Vantage HILOWS) ---

/** A hi/lo pair with the times each occurred. Times are day-only. */
export interface ConsoleHiLo {
  low: number | null;
  high: number | null;
  time_low: string | null;   // "HH:MM"
  time_high: string | null;
}

export interface ConsoleHiOnly {
  value: number | null;
  time: string | null;
}

export interface ConsolePeriod {
  day: ConsoleHiLo;
  month: ConsoleHiLo;
  year: ConsoleHiLo;
}

export interface ConsoleHiOnlyPeriod {
  day: ConsoleHiOnly;
  month: ConsoleHiOnly;
  year: ConsoleHiOnly;
}

/**
 * The console's own extremes, sampled continuously.
 *
 * Every value is nullable: an unpopulated sensor or a dashed reading
 * comes back as null rather than 0, which the parser works to preserve.
 */
export interface ConsoleHighsLows {
  barometer: ConsolePeriod;
  wind_speed: ConsoleHiOnlyPeriod;
  inside_temp: ConsolePeriod;
  inside_humidity: ConsolePeriod;
  outside_temp: ConsolePeriod;
  dew_point: ConsolePeriod;
  wind_chill: ConsoleHiOnlyPeriod;
  heat_index: ConsoleHiOnlyPeriod;
  thsw_index: ConsoleHiOnlyPeriod;
  solar_radiation: ConsoleHiOnlyPeriod;
  uv_index: ConsoleHiOnlyPeriod;
  rain_rate: ConsoleHiOnlyPeriod;
  rain_rate_hour_hi: number | null;
  /** Index 0 is the outside sensor; 1-7 are extras. Empty on a
   *  block that could not be parsed, so index with care. */
  humidities: ConsolePeriod[];
}

export interface ConsoleHighsLowsResponse {
  highs_lows: ConsoleHighsLows;
}

// --- Console reception diagnostics (Vantage) ---

/**
 * RXCHECK counters, plus the transmitter IDs the console reports hearing.
 *
 * Every counter is a total since station midnight, not a rate. One reading
 * says how the day has gone; two readings apart say how it is going now.
 *
 * `max_consecutive_received` counts a run of SUCCESSES — the manual's
 * "largest number of packets received in a row" — so a large value is
 * healthy. Read as consecutive misses it inverts completely, which is a
 * mistake that has already been made once in a diagnostic script.
 */
export interface SignalQuality {
  packets_received: number;
  missed: number;
  resync: number;
  max_consecutive_received: number;
  crc_errors: number;
  /**
   * Null when RECEIVERS failed, empty when the console answered with no
   * IDs — a Vue legitimately does the latter. Neither means "hearing
   * nothing"; the RXCHECK counters are what say that.
   */
  receivers: number[] | null;
}

/**
 * Radio state and per-unit crystal calibration via OPMODE.
 *
 * Undocumented Davis command, verified identical on Vue fw 2.12 and
 * fw 4.33 in the wire audit (see `reference/vantage_fw433_wire_audit.md`
 * §N3). Every field is a normalised integer; the wire's `TEMP CAL:`
 * key with a literal space is folded to `TEMP_CAL` by the driver.
 *
 * All fields optional because malformed lines are dropped by the driver
 * rather than crashing the whole read — a legitimately supported
 * console with a weird firmware may return a partial dict.
 */
export interface RadioState {
  TST?: number;
  TX?: number;
  RX?: number;
  HOP?: number;
  BAND?: number;
  CHAN?: number;
  DOM?: number;
  XTLCAL?: number;
  TEMP?: number;
  TEMP_CAL?: number;
}

// --- Vantage sensor calibration ---

/**
 * Per-sensor temperature/humidity offsets held in console EEPROM.
 *
 * Distinct from barometer calibration, which uses BAR= and has its own
 * types above. A field is absent when the console could not be read —
 * zero is a real calibration and must not stand in for "unknown".
 */
export interface VantageCalibrationOffsets {
  inside_temp?: number;
  outside_temp?: number;
  inside_humidity?: number;
  outside_humidity?: number;
}

export interface VantageCalibrationState {
  offsets: VantageCalibrationOffsets;
  /** "tenths_f" — a caller assuming whole degrees is off by 10x. */
  temp_units: string;
  humidity_units: string;
}

export interface VantageCalibrationResult {
  success: boolean;
  before: VantageCalibrationOffsets | null;
  after: VantageCalibrationOffsets | null;
}

export type VantageCalibrationField =
  | "inside_temp"
  | "outside_temp"
  | "inside_humidity"
  | "outside_humidity";

// --- Console location (Vantage) ---

/**
 * The console's own latitude/longitude, held in its EEPROM.
 *
 * Stored as signed tenths of a degree — ~11 km per step — so this can
 * never equal Kanfei's configured location exactly. Compare at
 * `resolution_deg`, not for equality.
 */
export interface ConsoleLocation {
  latitude: number;
  longitude: number;
  resolution_deg: number;
}

export interface ConsoleLocationPair {
  latitude: number;
  longitude: number;
}

export interface ConsoleLocationResult {
  success: boolean;
  before: ConsoleLocationPair | null;
  /** What the console holds after rounding — not what was sent. */
  after: ConsoleLocationPair | null;
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
  /**
   * Null on any station that is not a LinkDriver. Vantage calibration
   * uses different addresses and a different write procedure, so the
   * backend reports it unsupported rather than forcing it into this
   * five-field legacy shape.
   *
   * This was typed non-nullable while the backend had always been able
   * to return null, so `tsc` could not see the crash that null caused.
   */
  calibration: WeatherLinkCalibration | null;
  /** Which settings this station actually accepts. */
  supported?: {
    archive_period: boolean;
    sample_period: boolean;
    calibration: boolean;
    /**
     * Whether the station accepts BAR= barometer calibration (Vantage only).
     *
     * Optional because a daemon predating this key omits it. Read it as
     * `?? false` rather than sniffing a value the way `calibration` does —
     * there is no legacy signal to sniff, and false degrades to "panel
     * hidden on an old daemon", which is the correct behaviour.
     */
    barometer_cal?: boolean;
    /** PUTRAIN + CLRLOG (Vantage). */
    console_data_ops?: boolean;
    /** Console-held highs/lows (Vantage with LOOP2). */
    highs_lows?: boolean;
    /**
     * Per-sensor temperature/humidity offsets (Vantage, CALED/CALFIX).
     * Not `calibration` — that is the legacy five-field block, false
     * on a Vantage — and not `barometer_cal`, which is BAR=.
     */
    sensor_calibration?: boolean;
    /** Whether the console holds its own lat/lon (Vantage). */
    location?: boolean;
    /** RXCHECK reception diagnostics (Vantage). */
    signal_quality?: boolean;
    /** RAIN_YEAR_START — yearly-rain-reset month (Vantage). */
    rain_season?: boolean;
  };
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

// --- Map View ---

export interface NearbyStation {
  id: string;
  name: string;
  lat: number;
  lon: number;
  distance_mi: number;
  source: string;
  temp_f: number | null;
  wind_mph: number | null;
  wind_dir: number | null;
  wind_gust_mph: number | null;
  pressure_hpa: number | null;
  pressure_inhg: number | null;
  precip_in: number | null;
  updated: string | null;
}

export interface NearbyStationsResponse {
  stations: NearbyStation[];
  home_lat: number;
  home_lon: number;
  radius_mi: number;
  fetched_at: string;
}

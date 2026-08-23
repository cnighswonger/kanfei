/**
 * Compact panel showing station connection and health information.
 * On mobile: compact card that opens a modal with full details.
 */
import { useEffect, useState } from "react";
import { useWeatherData } from "../../context/WeatherDataContext.tsx";
import { syncStationTime } from "../../api/client.ts";
import { useCompact } from "../../dashboard/CompactContext.tsx";
import CompactCard from "../common/CompactCard.tsx";

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  try {
    const date = new Date(iso);
    return date.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "--";
  }
}

/**
 * Stall-detection thresholds for the Last Poll badge (sub-issue #474
 * of umbrella #472).  ``warning`` matches `/api/health`'s recovery
 * boundary — divergent numbers here would mean the operator sees the
 * frontend "clear" a stall the daemon's watchdog is still working on.
 * ``danger`` is a separate operator affordance: at 15 min the
 * likelihood the daemon is genuinely wedged (rather than a slow poll)
 * is high enough that we say so explicitly.
 */
const WARN_INTERVAL_MULTIPLIER = 3;
const WARN_FALLBACK_SECONDS = 180;
const DANGER_SECONDS = 900;

interface StallState {
  /** null when the badge is quiet (no lastPoll, or within threshold). */
  highlight: "warning" | "danger" | null;
  /** Suffix appended after the formatted timestamp; "" when quiet. */
  suffix: string;
}

/**
 * How stale is the last poll, relative to now?  Returns an operator
 * affordance for the Last Poll row.  Umbrella #472 documented the
 * failure mode this exists to surface: when the poller's serial write
 * wedges in the kernel, the timestamp freezes but nothing else on
 * screen signals it.
 */
function computeLastPollStall(
  iso: string | null,
  pollIntervalSec: number | null | undefined,
  nowMs: number,
): StallState {
  if (!iso) return { highlight: null, suffix: "" };
  const ts = Date.parse(iso);
  if (!Number.isFinite(ts)) return { highlight: null, suffix: "" };
  const ageSec = (nowMs - ts) / 1000;
  const warnAt =
    pollIntervalSec && pollIntervalSec > 0
      ? WARN_INTERVAL_MULTIPLIER * pollIntervalSec
      : WARN_FALLBACK_SECONDS;
  if (ageSec < warnAt) return { highlight: null, suffix: "" };
  const ageMin = Math.max(1, Math.round(ageSec / 60));
  if (ageSec >= DANGER_SECONDS) {
    return {
      highlight: "danger",
      suffix: ` — stalled ~${ageMin}m (logger may be wedged)`,
    };
  }
  return { highlight: "warning", suffix: ` — stalled ~${ageMin}m` };
}

interface StationClockComponents {
  year: number | null;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
}

/**
 * Advance the console's reported wall-clock components forward by
 * `elapsedMs` and format as `HH:MM:SS MM/DD` (or `HH:MM:SS MM/DD/YYYY`
 * when the station reported a year). All arithmetic goes through UTC to
 * keep the browser's local timezone from touching the values — the
 * components are treated as opaque wall-clock fields that just need to
 * roll forward by the elapsed delta, not as an instant in time.
 *
 * When `year` is null (older station), we synthesize a placeholder for
 * the arithmetic and drop it from the output so the format still matches
 * the backend's `station_time` string.
 */
function formatStationClock(c: StationClockComponents, elapsedMs: number): string {
  const yearPresent = c.year != null;
  const seedYear = c.year ?? 2000; // placeholder — arithmetic only, hidden from output
  const seedUtcMs = Date.UTC(seedYear, c.month - 1, c.day, c.hour, c.minute, c.second);
  const d = new Date(seedUtcMs + elapsedMs);
  const pad = (n: number) => n.toString().padStart(2, "0");
  const base = `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} ${pad(d.getUTCMonth() + 1)}/${pad(d.getUTCDate())}`;
  return yearPresent ? `${base}/${d.getUTCFullYear()}` : base;
}

function highlightColor(hl: "success" | "danger" | "warning" | null | undefined): string {
  if (hl === "success") return "var(--color-success)";
  if (hl === "danger") return "var(--color-danger)";
  if (hl === "warning") return "var(--color-warning)";
  return "var(--color-text)";
}

interface StatusRow {
  label: string;
  value: string;
  highlight?: "success" | "danger" | "warning" | null;
}

export default function StationStatus() {
  const { stationStatus, connected, wsConnected } = useWeatherData();
  const [syncing, setSyncing] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const isMobile = useCompact();

  // --- Live-ticked station clock ---
  //
  // The `/api/station` poll returns the console's wall-clock components
  // plus the server's UTC-epoch at the moment of the read. We advance
  // the components forward by `Date.now() - server_epoch_ms_at_read` and
  // format them as-is, without any timezone conversion. That keeps the
  // display faithful to what the console actually shows — the browser's
  // local timezone never touches the output — and avoids the false-alarm
  // Sync click that a 5-minute-stale readout triggers.
  //
  // Zero extra serial cost: this is pure extrapolation between snapshots.
  // Real console drift (crystal oscillator, seconds per week) shows up
  // as a small offset that persists until the next auto-sync.
  //
  // Fallback to the server-formatted string when the pair is unavailable
  // (disconnected, station doesn't support GETTIME, or first render
  // before the first successful poll).
  const components = stationStatus?.station_time_components ?? null;
  const readAnchor = stationStatus?.server_epoch_ms_at_read ?? null;
  const [, setTick] = useState(0);

  useEffect(() => {
    if (components == null || readAnchor == null) return;
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [components, readAnchor]);

  // Separate re-tick so the Last Poll stall badge (sub-issue #474) can
  // move without a fresh stationStatus arriving — the failure mode
  // it exists to surface is precisely that stationStatus stops
  // arriving.  10 s is well below the 3-min warning threshold and
  // 15-min danger threshold, so no visible latency in the transition.
  useEffect(() => {
    if (!stationStatus?.last_poll) return;
    const id = setInterval(() => setTick((n) => n + 1), 10_000);
    return () => clearInterval(id);
  }, [stationStatus?.last_poll]);

  const lastPollStall = computeLastPollStall(
    stationStatus?.last_poll ?? null,
    stationStatus?.poll_interval,
    Date.now(),
  );

  const stationClockDisplay =
    components != null && readAnchor != null
      ? formatStationClock(components, Date.now() - readAnchor)
      : (stationStatus?.station_time ?? "--");

  // Firmware string — prefer the version number (e.g. "1.90") when the
  // station reports it via NVER; fall back to the free-form build date
  // (e.g. "Aug 15 2013") when it does not.  Both null on legacy stations,
  // and on Vantage between connect and first VER response — hide the row
  // in that case rather than showing an empty value.
  const firmware =
    stationStatus?.firmware_version ?? stationStatus?.firmware_date ?? null;

  // Product SKU from the undocumented IDENT command (see
  // reference/vantage_fw433_wire_audit.md).  On Davis this is the
  // 4-digit product-bundle number (e.g. "6351" for Vantage Vue
  // Wireless with WeatherLink IP), distinct from the station model
  // reported by station_type_code.  Null on stations that don't
  // support IDENT — legacy, LinkDriver, or before the connect
  // handshake completes.
  const productSku = stationStatus?.product_sku ?? null;

  // Battery status — surfaced from `sensor_readings.extra_json` on every
  // Vantage poll (see #236).  Two rows: transmitter health (OK / Low: IDs)
  // and console voltage where reported.  Hidden entirely when the driver
  // doesn't provide either — non-Davis stations, or Davis before the
  // first LOOP1 with battery bits parses.
  const battery = stationStatus?.battery ?? null;
  const batteryRows: StatusRow[] = [];
  if (battery != null) {
    const lowIds = battery.transmitters_low;
    if (lowIds.length > 0) {
      batteryRows.push({
        label: "Transmitters",
        value: `Low: TX${lowIds.join(", TX")}`,
        highlight: "danger",
      });
    } else if (battery.raw_transmitter_bitmask != null) {
      // We know the bitmask was reported (empty list means it was 0);
      // don't show a row when we don't have TX data at all.
      batteryRows.push({
        label: "Transmitters",
        value: "OK",
        highlight: "success",
      });
    }
    if (battery.console_voltage != null) {
      batteryRows.push({
        label: "Console Battery",
        // A Davis Vue's supercap+coin cell floats ~4.7V under normal
        // operation. Below 4V the coin cell backup is likely depleted;
        // warn but don't scream — this is diagnostic, not immediate.
        value: `${battery.console_voltage.toFixed(2)} V`,
        highlight: battery.console_voltage < 4.0 ? "warning" : null,
      });
    }
  }

  const rows: StatusRow[] = [
    {
      label: "Station",
      value: stationStatus?.type_name ?? "--",
    },
    ...(productSku
      ? [{ label: "Product #", value: productSku } as StatusRow]
      : []),
    ...(firmware ? [{ label: "Firmware", value: firmware } as StatusRow] : []),
    ...batteryRows,
    {
      label: "Connected",
      value: stationStatus?.connected ? "Yes" : "No",
      highlight: stationStatus?.connected ? "success" : "danger",
    },
    {
      label: "WebSocket",
      value: wsConnected ? "Open" : "Closed",
      highlight: wsConnected ? "success" : "warning",
    },
    {
      label: "Backend Link",
      value: connected ? "Up" : "Down",
      highlight: connected ? "success" : "danger",
    },
    {
      label: "Uptime",
      value: stationStatus
        ? formatUptime(stationStatus.uptime_seconds)
        : "--",
    },
    {
      label: "Poll Interval",
      value: stationStatus ? `${stationStatus.poll_interval}s` : "--",
    },
    {
      label: "CRC Errors",
      value: stationStatus ? String(stationStatus.crc_errors) : "--",
      highlight:
        stationStatus && stationStatus.crc_errors > 0 ? "warning" : null,
    },
    {
      label: "Timeouts",
      value: stationStatus ? String(stationStatus.timeouts) : "--",
      highlight:
        stationStatus && stationStatus.timeouts > 0 ? "warning" : null,
    },
    {
      label: "Archive Records",
      value: stationStatus?.archive_records != null
        ? stationStatus.archive_records.toLocaleString()
        : "--",
    },
    {
      label: "Last Poll",
      // Sub-issue #474 of umbrella #472.  When the poller's serial
      // write wedges in the kernel, the timestamp freezes; the badge
      // tint + suffix name the failure explicitly instead of leaving
      // the reader to notice the number stopped moving.  Thresholds
      // match `/api/health` (from #473) so the frontend affordance
      // and the external monitor tell the same story.
      value:
        formatTime(stationStatus?.last_poll ?? null) + lastPollStall.suffix,
      highlight: lastPollStall.highlight,
    },
  ];

  const handleSync = async () => {
    setSyncing(true);
    try {
      await syncStationTime();
    } catch {
      /* ignore */
    } finally {
      setSyncing(false);
    }
  };

  // --- Shared status detail content (used in both desktop card and mobile modal) ---
  const statusContent = (
    <>
      {/* Station Time row */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "10px",
          padding: "6px 8px",
          background: "var(--color-bg, rgba(0,0,0,0.15))",
          borderRadius: "8px",
        }}
      >
        <div>
          <span
            style={{
              fontSize: "calc(11px * var(--font-scale))",
              fontFamily: "var(--font-body)",
              color: "var(--color-text-muted)",
              marginRight: "8px",
            }}
          >
            Station Clock
          </span>
          <span
            style={{
              fontSize: "calc(12px * var(--font-scale))",
              fontFamily: "var(--font-gauge)",
              fontWeight: "bold",
              color: "var(--color-text)",
            }}
          >
            {stationClockDisplay}
          </span>
        </div>
        <button
          onClick={handleSync}
          disabled={syncing || !stationStatus?.connected}
          style={{
            fontSize: "calc(10px * var(--font-scale))",
            fontFamily: "var(--font-body)",
            padding: "2px 8px",
            background: "var(--color-bg-card)",
            color: "var(--color-text-secondary)",
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            cursor: syncing ? "wait" : "pointer",
            opacity: syncing || !stationStatus?.connected ? 0.6 : 1,
          }}
        >
          {syncing ? "Syncing..." : "Sync"}
        </button>
      </div>

      {/* Status rows grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "8px 16px",
        }}
      >
        {rows.map((row) => (
          <div
            key={row.label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              gap: "8px",
            }}
          >
            <span
              style={{
                fontSize: "calc(11px * var(--font-scale))",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-muted)",
              }}
            >
              {row.label}
            </span>
            <span
              style={{
                fontSize: "calc(12px * var(--font-scale))",
                fontFamily: "var(--font-gauge)",
                fontWeight: "bold",
                color: highlightColor(row.highlight),
              }}
            >
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </>
  );

  // --- Mobile: compact card + modal ---
  if (isMobile) {
    const isConnected = stationStatus?.connected ?? false;
    return (
      <>
        <CompactCard
          label="Station Status"
          onClick={() => setShowModal(true)}
          secondary={
            stationStatus
              ? formatUptime(stationStatus.uptime_seconds)
              : undefined
          }
        >
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor: isConnected
                  ? "var(--color-success)"
                  : "var(--color-danger)",
                display: "inline-block",
                boxShadow: isConnected
                  ? "0 0 6px var(--color-success)"
                  : "0 0 6px var(--color-danger)",
              }}
            />
            <span
              style={{
                fontSize: "calc(16px * var(--font-scale))",
                fontFamily: "var(--font-gauge)",
                fontWeight: "bold",
                color: highlightColor(isConnected ? "success" : "danger"),
              }}
            >
              {isConnected ? "Connected" : "Disconnected"}
            </span>
          </div>
        </CompactCard>

        {showModal && (
          <div
            onClick={() => setShowModal(false)}
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
                background: "var(--color-bg-card)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--gauge-border-radius, 16px)",
                padding: "20px",
                width: "90vw",
                maxWidth: 400,
                maxHeight: "80vh",
                overflowY: "auto",
                boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
              }}
            >
              <div
                style={{
                  fontSize: "calc(12px * var(--font-scale))",
                  fontFamily: "var(--font-body)",
                  color: "var(--color-text-secondary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.5px",
                  marginBottom: "12px",
                  textAlign: "center",
                }}
              >
                Station Status
              </div>
              {statusContent}
            </div>
          </div>
        )}
      </>
    );
  }

  // --- Desktop: full inline card ---
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        padding: "16px",
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        boxShadow: "var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))",
        border: "1px solid var(--color-border)",
      }}
    >
      <div
        style={{
          fontSize: "calc(12px * var(--font-scale))",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          marginBottom: "12px",
          textAlign: "center",
        }}
      >
        Station Status
      </div>
      {statusContent}
    </div>
  );
}

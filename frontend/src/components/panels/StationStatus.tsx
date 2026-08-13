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
 * Format an epoch timestamp as `HH:MM:SS MM/DD` in the browser's local
 * timezone — the same shape the backend produces for `station_time`, so
 * the live-ticked display doesn't visually shift when it takes over
 * from the initial server-rendered string.
 */
function formatStationClock(epochMs: number): string {
  const d = new Date(epochMs);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())} ${pad(d.getMonth() + 1)}/${pad(d.getDate())}`;
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
  // Capture the (station_epoch, wall_epoch) pair from each status poll and
  // display station_epoch + (Date.now() - wall_epoch), ticked every second.
  // The status poll runs every 5 min while connected; without this, the
  // displayed clock ages up to 5 min between polls and looks stale enough
  // to trigger a false-alarm Sync click. Zero extra serial cost — we're
  // extrapolating from a snapshot, not asking the console again.
  //
  // Fallback to the server-formatted string when the pair is unavailable
  // (disconnected, station doesn't support GETTIME, or first render before
  // the first successful poll).
  const stationEpochMs = stationStatus?.station_time_epoch_ms ?? null;
  const [clockOffsetMs, setClockOffsetMs] = useState<number | null>(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    if (stationEpochMs == null) {
      setClockOffsetMs(null);
      return;
    }
    setClockOffsetMs(stationEpochMs - Date.now());
  }, [stationEpochMs]);

  useEffect(() => {
    if (clockOffsetMs == null) return;
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [clockOffsetMs]);

  const stationClockDisplay =
    clockOffsetMs != null
      ? formatStationClock(Date.now() + clockOffsetMs)
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

  const rows: StatusRow[] = [
    {
      label: "Station",
      value: stationStatus?.type_name ?? "--",
    },
    ...(productSku
      ? [{ label: "Product #", value: productSku } as StatusRow]
      : []),
    ...(firmware ? [{ label: "Firmware", value: firmware } as StatusRow] : []),
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
      value: formatTime(stationStatus?.last_poll ?? null),
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

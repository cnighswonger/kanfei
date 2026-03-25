/**
 * Setup wizard Step 1: Station type selection and connection configuration.
 *
 * Phase 1: Select your station from the driver catalog.
 * Phase 2: Configure connection (serial port, IP address, etc.) based on driver.
 *
 * Designed so auto-discovery can slot in as a future Phase 1.5 without
 * restructuring the component.
 */
import { useState, useEffect, useCallback } from "react";
import {
  fetchSerialPorts,
  probeSerialPort,
  autoDetectStation,
} from "../../api/client.ts";
import { API_BASE } from "../../utils/constants.ts";

interface DriverInfo {
  type: string;
  name: string;
  connection: string;
  description: string;
  config_fields: string[];
}

interface StepStationProps {
  driverType: string;
  serialPort: string;
  baudRate: number;
  stationType: string | null;
  weatherlinkIp: string;
  weatherlinkPort: number;
  ecowittIp: string;
  tempestHubSn: string;
  ambientListenPort: number;
  onChange: (partial: Record<string, unknown>) => void;
}

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "12px",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const labelStyle: React.CSSProperties = {
  fontSize: "13px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "6px",
  display: "block",
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

const inputStyle: React.CSSProperties = {
  ...selectStyle,
  cursor: "text",
};

const btnStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "13px",
  padding: "8px 16px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  cursor: "pointer",
  transition: "background 0.15s",
};

const btnAccent: React.CSSProperties = {
  ...btnStyle,
  background: "var(--color-accent)",
  borderColor: "var(--color-accent)",
  color: "#fff",
  fontWeight: 600,
};


export default function StepStation({
  driverType,
  serialPort,
  baudRate,
  stationType,
  weatherlinkIp,
  weatherlinkPort,
  ecowittIp,
  tempestHubSn,
  ambientListenPort,
  onChange,
}: StepStationProps) {
  const [drivers, setDrivers] = useState<DriverInfo[]>([]);
  const [ports, setPorts] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [probing, setProbing] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch driver catalog
  useEffect(() => {
    fetch(`${API_BASE}/api/station/drivers`)
      .then((r) => r.json())
      .then(setDrivers)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // Fetch serial ports when a serial driver is selected
  const selectedDriver = drivers.find((d) => d.type === driverType);
  const isSerial = selectedDriver?.connection === "serial";

  const refreshPorts = useCallback(() => {
    fetchSerialPorts()
      .then((result) => {
        setPorts(result.ports);
        if (result.ports.length > 0 && !serialPort) {
          onChange({ serialPort: result.ports[0] });
        }
      })
      .catch(() => setPorts([]));
  }, [serialPort, onChange]);

  useEffect(() => {
    if (isSerial) refreshPorts();
  }, [isSerial, refreshPorts]);

  const handleAutoDetect = useCallback(async () => {
    setDetecting(true);
    setError(null);
    onChange({ stationType: null });
    try {
      const result = await autoDetectStation();
      if (result.found) {
        onChange({
          serialPort: result.port ?? serialPort,
          baudRate: result.baud_rate ?? baudRate,
          stationType: result.station_type,
          driverType: result.driver_type ?? "legacy",
        });
      } else {
        setError(
          `No station found. Tried ${result.attempts.length} port/baud combinations.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDetecting(false);
    }
  }, [serialPort, baudRate, onChange]);

  const handleTestConnection = useCallback(async () => {
    if (!serialPort) return;
    setProbing(true);
    setError(null);
    onChange({ stationType: null });
    try {
      const result = await probeSerialPort(serialPort, baudRate);
      if (result.success) {
        onChange({
          stationType: result.station_type,
          driverType: result.driver_type ?? "legacy",
        });
      } else {
        setError(result.error ?? "Connection failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProbing(false);
    }
  }, [serialPort, baudRate, onChange]);

  const busy = detecting || probing || loading;

  return (
    <div>
      {/* Driver selection */}
      <p
        style={{
          fontSize: "14px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
          marginBottom: "20px",
          lineHeight: 1.5,
        }}
      >
        Select your weather station, then configure its connection.
      </p>

      <div style={{ marginBottom: "24px" }}>
        <div style={cardStyle}>
          <label style={labelStyle}>Weather Station</label>
          <select
            style={selectStyle}
            value={driverType}
            onChange={(e) => {
              onChange({ driverType: e.target.value, stationType: null });
              setError(null);
            }}
          >
            {drivers.map((d) => (
              <option key={d.type} value={d.type}>
                {d.name}
              </option>
            ))}
          </select>
          {selectedDriver && (
            <p
              style={{
                fontSize: "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-muted)",
                marginTop: "8px",
                marginBottom: 0,
                lineHeight: 1.4,
              }}
            >
              {selectedDriver.description}
            </p>
          )}
        </div>
      </div>

      {/* Connection config — adapts to selected driver */}
      {selectedDriver && (
        <div style={cardStyle}>
          <h4
            style={{
              margin: "0 0 12px 0",
              fontSize: "14px",
              fontFamily: "var(--font-heading)",
              color: "var(--color-text)",
            }}
          >
            Connection Settings
          </h4>

          {/* Serial drivers */}
          {isSerial && (
            <>
              <div style={{ textAlign: "center", marginBottom: "16px" }}>
                <button
                  style={{
                    ...btnAccent,
                    fontSize: "14px",
                    padding: "10px 28px",
                    opacity: busy ? 0.6 : 1,
                    cursor: busy ? "wait" : "pointer",
                  }}
                  onClick={handleAutoDetect}
                  disabled={busy}
                >
                  {detecting ? "Scanning..." : "Auto-Detect"}
                </button>
                <p
                  style={{
                    fontSize: "11px",
                    color: "var(--color-text-muted)",
                    marginTop: "6px",
                    marginBottom: 0,
                  }}
                >
                  Scans all serial ports automatically
                </p>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "16px",
                }}
              >
                <div>
                  <label style={labelStyle}>
                    Serial Port
                    <button
                      style={{
                        ...btnStyle,
                        fontSize: "11px",
                        padding: "2px 8px",
                        marginLeft: "8px",
                      }}
                      onClick={refreshPorts}
                      disabled={busy}
                    >
                      Refresh
                    </button>
                  </label>
                  <select
                    style={selectStyle}
                    value={serialPort}
                    onChange={(e) =>
                      onChange({ serialPort: e.target.value, stationType: null })
                    }
                    disabled={busy}
                  >
                    {ports.length === 0 && (
                      <option value="">No ports detected</option>
                    )}
                    {ports.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={labelStyle}>Baud Rate</label>
                  <select
                    style={selectStyle}
                    value={baudRate}
                    onChange={(e) =>
                      onChange({
                        baudRate: parseInt(e.target.value),
                        stationType: null,
                      })
                    }
                    disabled={busy}
                  >
                    <option value={19200}>19200 (Vantage Pro/Pro2/Vue)</option>
                    <option value={2400}>2400 (Weather Monitor/Wizard)</option>
                    <option value={1200}>1200</option>
                  </select>
                </div>
              </div>

              <div style={{ marginTop: "12px" }}>
                <button
                  style={{
                    ...btnStyle,
                    opacity: busy || !serialPort ? 0.6 : 1,
                    cursor: busy || !serialPort ? "not-allowed" : "pointer",
                  }}
                  onClick={handleTestConnection}
                  disabled={busy || !serialPort}
                >
                  {probing ? "Testing..." : "Test Connection"}
                </button>
              </div>
            </>
          )}

          {/* Network drivers (WeatherLink IP/Live, Ecowitt) */}
          {selectedDriver.connection === "network" && (
            <div>
              <div style={{ marginBottom: "12px" }}>
                <label style={labelStyle}>
                  {driverType === "ecowitt" ? "Gateway" : "Device"} IP Address
                </label>
                <input
                  style={inputStyle}
                  type="text"
                  placeholder="192.168.1.100"
                  value={driverType === "ecowitt" ? ecowittIp : weatherlinkIp}
                  onChange={(e) =>
                    onChange(
                      driverType === "ecowitt"
                        ? { ecowittIp: e.target.value }
                        : { weatherlinkIp: e.target.value },
                    )
                  }
                />
              </div>
              {driverType === "weatherlink_ip" && (
                <div>
                  <label style={labelStyle}>TCP Port</label>
                  <input
                    style={inputStyle}
                    type="number"
                    value={weatherlinkPort}
                    onChange={(e) =>
                      onChange({ weatherlinkPort: parseInt(e.target.value) || 22222 })
                    }
                  />
                </div>
              )}
            </div>
          )}

          {/* UDP (Tempest) */}
          {selectedDriver.connection === "udp" && (
            <div>
              <label style={labelStyle}>Hub Serial Number (optional)</label>
              <input
                style={inputStyle}
                type="text"
                placeholder="Leave blank to accept any hub"
                value={tempestHubSn}
                onChange={(e) => onChange({ tempestHubSn: e.target.value })}
              />
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--color-text-muted)",
                  marginTop: "6px",
                }}
              >
                The Tempest hub broadcasts on your local network. Kanfei listens
                automatically — no IP address needed.
              </p>
            </div>
          )}

          {/* HTTP push (Ambient) */}
          {selectedDriver.connection === "http_push" && (
            <div>
              <label style={labelStyle}>Listen Port</label>
              <input
                style={inputStyle}
                type="number"
                value={ambientListenPort}
                onChange={(e) =>
                  onChange({ ambientListenPort: parseInt(e.target.value) || 8080 })
                }
              />
              <p
                style={{
                  fontSize: "12px",
                  color: "var(--color-text-muted)",
                  marginTop: "6px",
                }}
              >
                Configure your Ambient Weather station to push data to this
                computer's IP on this port. Use Wunderground or Ecowitt custom
                server settings on the station.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Detection result */}
      {stationType && (
        <div
          style={{
            ...cardStyle,
            background: "var(--color-success, #16a34a)",
            border: "none",
            color: "#fff",
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontSize: "16px",
              fontWeight: "bold",
              fontFamily: "var(--font-heading)",
            }}
          >
            Station Found: {stationType}
          </div>
          {isSerial && (
            <div style={{ fontSize: "13px", marginTop: "4px", opacity: 0.85 }}>
              {serialPort} at {baudRate} baud
            </div>
          )}
        </div>
      )}

      {error && (
        <div
          style={{
            ...cardStyle,
            borderColor: "var(--color-danger)",
            color: "var(--color-danger)",
            fontSize: "13px",
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

/**
 * Setup wizard Step 1: Serial port detection and configuration.
 */
import { useState, useEffect, useCallback } from "react";
import {
  fetchSerialPorts,
  probeSerialPort,
  autoDetectStation,
} from "../../api/client.ts";

interface StepSerialProps {
  serialPort: string;
  baudRate: number;
  stationType: string | null;
  driverType: string;
  onChange: (partial: {
    serialPort?: string;
    baudRate?: number;
    stationType?: string | null;
    driverType?: string;
  }) => void;
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

export default function StepSerial({
  serialPort,
  baudRate,
  stationType,
  driverType: _driverType,
  onChange,
}: StepSerialProps) {
  const [ports, setPorts] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [probing, setProbing] = useState(false);
  const [detecting, setDetecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshPorts = useCallback(() => {
    setLoading(true);
    fetchSerialPorts()
      .then((result) => {
        setPorts(result.ports);
        if (result.ports.length > 0 && !serialPort) {
          onChange({ serialPort: result.ports[0] });
        }
      })
      .catch(() => setPorts([]))
      .finally(() => setLoading(false));
  }, [serialPort, onChange]);

  useEffect(() => {
    refreshPorts();
  }, [refreshPorts]);

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
      <p
        style={{
          fontSize: "14px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
          marginBottom: "20px",
          lineHeight: 1.5,
        }}
      >
        Connect your WeatherLink cable and click Auto-Detect, or manually
        select the serial port and baud rate below.
      </p>

      {/* Auto-detect card */}
      <div style={{ ...cardStyle, textAlign: "center" }}>
        <button
          style={{
            ...btnAccent,
            fontSize: "15px",
            padding: "12px 32px",
            opacity: busy ? 0.6 : 1,
            cursor: busy ? "wait" : "pointer",
          }}
          onClick={handleAutoDetect}
          disabled={busy}
          aria-label="Auto-detect weather station"
        >
          {detecting ? "Scanning..." : "Auto-Detect Station"}
        </button>
        <p
          style={{
            fontSize: "12px",
            color: "var(--color-text-muted)",
            marginTop: "8px",
            marginBottom: 0,
          }}
        >
          Scans all ports at 19200, 2400, and 1200 baud
        </p>
      </div>

      {/* Manual config */}
      <div style={cardStyle}>
        <div
          style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}
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
                aria-label="Refresh serial ports"
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
              aria-label="Serial port"
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
              aria-label="Baud rate"
            >
              <option value={19200}>19200 (Vantage Pro)</option>
              <option value={2400}>2400 (WeatherLink)</option>
              <option value={1200}>1200</option>
            </select>
          </div>
        </div>

        <div style={{ marginTop: "16px" }}>
          <button
            style={{
              ...btnStyle,
              opacity: busy || !serialPort ? 0.6 : 1,
              cursor: busy || !serialPort ? "not-allowed" : "pointer",
            }}
            onClick={handleTestConnection}
            disabled={busy || !serialPort}
            aria-label="Test serial connection"
          >
            {probing ? "Testing..." : "Test Connection"}
          </button>
        </div>
      </div>

      {/* Result */}
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
          <div
            style={{
              fontSize: "13px",
              marginTop: "4px",
              opacity: 0.85,
            }}
          >
            {serialPort} at {baudRate} baud
          </div>
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

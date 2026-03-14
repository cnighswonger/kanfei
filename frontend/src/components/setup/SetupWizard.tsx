/**
 * First-run setup wizard.
 * Full-screen overlay that walks new users through serial port detection,
 * location selection, and unit preferences.
 */
import { useState, useCallback } from "react";
import { completeSetup } from "../../api/client.ts";
import type { SetupConfig } from "../../api/types.ts";
import StepSerial from "./StepSerial.tsx";
import StepLocation from "./StepLocation.tsx";
import StepPreferences from "./StepPreferences.tsx";

interface SetupWizardProps {
  onComplete: () => void;
}

interface WizardState {
  serialPort: string;
  baudRate: number;
  stationType: string | null;
  driverType: string;
  latitude: number;
  longitude: number;
  elevation: number;
  tempUnit: string;
  pressureUnit: string;
  windUnit: string;
  rainUnit: string;
  metarEnabled: boolean;
  metarStation: string;
  nwsEnabled: boolean;
}

const STEPS = ["Station", "Location", "Preferences"] as const;

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 10000,
  background: "var(--color-bg)",
  overflow: "auto",
};

const containerStyle: React.CSSProperties = {
  maxWidth: "640px",
  margin: "0 auto",
  padding: "40px 24px",
};

const headerStyle: React.CSSProperties = {
  textAlign: "center",
  marginBottom: "32px",
};

const titleStyle: React.CSSProperties = {
  fontSize: "28px",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
  margin: "0 0 8px 0",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "14px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  margin: 0,
};

const progressBar: React.CSSProperties = {
  display: "flex",
  justifyContent: "center",
  gap: "8px",
  marginBottom: "32px",
};

const btnStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "10px 24px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  cursor: "pointer",
  fontWeight: 500,
};

const btnPrimary: React.CSSProperties = {
  ...btnStyle,
  background: "var(--color-accent)",
  borderColor: "var(--color-accent)",
  color: "#fff",
  fontWeight: 600,
};

export default function SetupWizard({ onComplete }: SetupWizardProps) {
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [state, setState] = useState<WizardState>({
    serialPort: "",
    baudRate: 2400,
    stationType: null,
    driverType: "legacy",
    latitude: 0,
    longitude: 0,
    elevation: 0,
    tempUnit: "F",
    pressureUnit: "inHg",
    windUnit: "mph",
    rainUnit: "in",
    metarEnabled: false,
    metarStation: "",
    nwsEnabled: false,
  });

  const handleChange = useCallback(
    (partial: Partial<WizardState>) => {
      setState((prev) => ({ ...prev, ...partial }));
    },
    [],
  );

  const canAdvance = (): boolean => {
    if (step === 0) return !!state.stationType;
    if (step === 1)
      return state.latitude !== 0 || state.longitude !== 0;
    return true;
  };

  const handleFinish = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const config: SetupConfig = {
        serial_port: state.serialPort,
        baud_rate: state.baudRate,
        station_driver_type: state.driverType,
        latitude: state.latitude,
        longitude: state.longitude,
        elevation: state.elevation,
        temp_unit: state.tempUnit,
        pressure_unit: state.pressureUnit,
        wind_unit: state.windUnit,
        rain_unit: state.rainUnit,
        metar_enabled: state.metarEnabled,
        metar_station: state.metarStation,
        nws_enabled: state.nwsEnabled,
      };
      await completeSetup(config);
      onComplete();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }, [state, onComplete]);

  const isLast = step === STEPS.length - 1;

  return (
    <div style={overlayStyle}>
      <div style={containerStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <h1 style={titleStyle}>Weather Station Setup</h1>
          <p style={subtitleStyle}>
            Step {step + 1} of {STEPS.length}: {STEPS[step]}
          </p>
        </div>

        {/* Progress dots */}
        <div style={progressBar}>
          {STEPS.map((_, i) => (
            <div
              key={i}
              style={{
                width: "10px",
                height: "10px",
                borderRadius: "50%",
                background:
                  i <= step
                    ? "var(--color-accent)"
                    : "var(--color-border)",
                transition: "background 0.2s",
              }}
            />
          ))}
        </div>

        {/* Step content */}
        <div style={{ marginBottom: "32px" }}>
          {step === 0 && (
            <StepSerial
              serialPort={state.serialPort}
              baudRate={state.baudRate}
              stationType={state.stationType}
              driverType={state.driverType}
              onChange={handleChange}
            />
          )}
          {step === 1 && (
            <StepLocation
              latitude={state.latitude}
              longitude={state.longitude}
              elevation={state.elevation}
              onChange={handleChange}
            />
          )}
          {step === 2 && (
            <StepPreferences
              tempUnit={state.tempUnit}
              pressureUnit={state.pressureUnit}
              windUnit={state.windUnit}
              rainUnit={state.rainUnit}
              metarEnabled={state.metarEnabled}
              metarStation={state.metarStation}
              nwsEnabled={state.nwsEnabled}
              onChange={handleChange}
            />
          )}
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              fontSize: "13px",
              color: "var(--color-danger)",
              marginBottom: "16px",
              padding: "12px",
              borderRadius: "8px",
              border: "1px solid var(--color-danger)",
              background: "var(--color-bg-card)",
            }}
          >
            {error}
          </div>
        )}

        {/* Navigation */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <button
            style={{
              ...btnStyle,
              visibility: step > 0 ? "visible" : "hidden",
            }}
            onClick={() => setStep((s) => s - 1)}
            disabled={submitting}
          >
            Back
          </button>

          {isLast ? (
            <button
              style={{
                ...btnPrimary,
                opacity: submitting ? 0.6 : 1,
                cursor: submitting ? "wait" : "pointer",
              }}
              onClick={handleFinish}
              disabled={submitting}
            >
              {submitting ? "Saving..." : "Finish Setup"}
            </button>
          ) : (
            <button
              style={{
                ...btnPrimary,
                opacity: canAdvance() ? 1 : 0.5,
                cursor: canAdvance() ? "pointer" : "not-allowed",
              }}
              onClick={() => setStep((s) => s + 1)}
              disabled={!canAdvance()}
            >
              Next
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

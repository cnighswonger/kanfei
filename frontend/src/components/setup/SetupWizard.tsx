/**
 * First-run setup wizard.
 * Full-screen overlay that walks new users through serial port detection,
 * location selection, and unit preferences.
 */
import { useState, useCallback } from "react";
import { completeSetup, setupAdmin } from "../../api/client.ts";
import type { SetupConfig } from "../../api/types.ts";
import StepStation from "./StepStation.tsx";
import StepLocation from "./StepLocation.tsx";
import StepPreferences from "./StepPreferences.tsx";
import StepAccount from "./StepAccount.tsx";

interface SetupWizardProps {
  onComplete: () => void;
}

interface WizardState {
  serialPort: string;
  baudRate: number;
  stationType: string | null;
  driverType: string;
  weatherlinkIp: string;
  weatherlinkPort: number;
  ecowittIp: string;
  tempestHubSn: string;
  ambientListenPort: number;
  // Public-droplet setup only (issue #336 Phase 4).  Sent as
  // public_mode_ingest_secret via /api/setup/complete so the same
  // pass-through writer already used for every other config key
  // lands it in station_config.
  publicModeIngestSecret: string;
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
  adminUsername: string;
  adminPassword: string;
  adminPasswordConfirm: string;
}

const STEPS = ["Station", "Location", "Preferences", "Account"] as const;

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
  fontSize: "calc(28px * var(--font-scale))",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
  margin: "0 0 8px 0",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: "calc(14px * var(--font-scale))",
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
  fontSize: "calc(14px * var(--font-scale))",
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
    weatherlinkIp: "",
    weatherlinkPort: 22222,
    ecowittIp: "",
    tempestHubSn: "",
    ambientListenPort: 8080,
    publicModeIngestSecret: "",
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
    adminUsername: "admin",
    adminPassword: "",
    adminPasswordConfirm: "",
  });

  const handleChange = useCallback(
    (partial: Partial<WizardState>) => {
      setState((prev) => ({ ...prev, ...partial }));
    },
    [],
  );

  const canAdvance = (): boolean => {
    if (step === 0) {
      // Serial drivers need a detected station type; others just need a driver selection
      const isSerial = ["legacy", "vantage"].includes(state.driverType);
      if (isSerial) return !!state.stationType;
      // Network drivers need an IP
      if (["weatherlink_ip", "weatherlink_live"].includes(state.driverType))
        return !!state.weatherlinkIp;
      if (state.driverType === "ecowitt") return !!state.ecowittIp;
      // Public droplet needs a non-trivial ingest secret so the
      // operator can't accidentally publish a droplet with an empty
      // or too-short shared credential.  16 chars is short enough to
      // paste but long enough to resist casual guessing; a
      // paranoid operator can use anything longer.
      if (state.driverType === "public_relay")
        return state.publicModeIngestSecret.length >= 16;
      // Tempest and Ambient can proceed with defaults
      return !!state.driverType;
    }
    if (step === 1)
      return state.latitude !== 0 || state.longitude !== 0;
    if (step === 3) {
      // Public droplet has no admin account (require_admin bypass on
      // that mode covers reads; there is nothing to authenticate).
      // Let the operator click Finish without typing a password.
      if (state.driverType === "public_relay") return true;
      return (
        state.adminUsername.length >= 3 &&
        state.adminPassword.length >= 8 &&
        state.adminPassword === state.adminPasswordConfirm
      );
    }
    return true;
  };

  const handleFinish = useCallback(async () => {
    setSubmitting(true);
    setError(null);
    try {
      const isPublicDroplet = state.driverType === "public_relay";
      const config: SetupConfig = {
        serial_port: state.serialPort,
        baud_rate: state.baudRate,
        station_driver_type: state.driverType,
        weatherlink_ip: state.weatherlinkIp,
        weatherlink_port: state.weatherlinkPort,
        ecowitt_ip: state.ecowittIp,
        tempest_hub_sn: state.tempestHubSn,
        ambient_listen_port: state.ambientListenPort,
        // Trim so a stray paste-tab or leading space doesn't create
        // a bearer that fails to match the droplet's stored copy —
        // constant-time compare has no notion of "close enough".
        public_mode_ingest_secret: state.publicModeIngestSecret.trim(),
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
      // Public droplet has NO admin account: the require_admin
      // bypass is what makes the read-only Settings UI browsable to
      // guests, and the write-block middleware fires as soon as
      // completeSetup commits ``station_driver_type = public_relay``.
      // Calling setup-admin here would be blocked by that middleware
      // (POST outside the ingest allowlist → 403), leaving the
      // droplet marked "setup complete" but the wizard in an error
      // state.  Codex round 1 on PR #340 caught this.
      if (!isPublicDroplet) {
        await setupAdmin(state.adminUsername, state.adminPassword);
      }
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
            <StepStation
              driverType={state.driverType}
              serialPort={state.serialPort}
              baudRate={state.baudRate}
              stationType={state.stationType}
              weatherlinkIp={state.weatherlinkIp}
              weatherlinkPort={state.weatherlinkPort}
              ecowittIp={state.ecowittIp}
              tempestHubSn={state.tempestHubSn}
              ambientListenPort={state.ambientListenPort}
              publicModeIngestSecret={state.publicModeIngestSecret}
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
          {step === 3 && (
            <StepAccount
              adminUsername={state.adminUsername}
              adminPassword={state.adminPassword}
              adminPasswordConfirm={state.adminPasswordConfirm}
              driverType={state.driverType}
              onChange={handleChange}
            />
          )}
        </div>

        {/* Error */}
        {error && (
          <div
            style={{
              fontSize: "calc(13px * var(--font-scale))",
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

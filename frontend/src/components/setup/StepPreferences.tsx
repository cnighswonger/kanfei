/**
 * Setup wizard Step 3: Unit preferences and service toggles.
 */

interface StepPreferencesProps {
  tempUnit: string;
  pressureUnit: string;
  windUnit: string;
  rainUnit: string;
  metarEnabled: boolean;
  metarStation: string;
  nwsEnabled: boolean;
  onChange: (
    partial: Partial<{
      tempUnit: string;
      pressureUnit: string;
      windUnit: string;
      rainUnit: string;
      metarEnabled: boolean;
      metarStation: string;
      nwsEnabled: boolean;
    }>,
  ) => void;
}

const labelStyle: React.CSSProperties = {
  fontSize: "13px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "6px",
  display: "block",
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
  maxWidth: "200px",
  boxSizing: "border-box",
};

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "12px",
  border: "1px solid var(--color-border)",
  padding: "20px",
  marginBottom: "16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 16px 0",
  fontSize: "16px",
  fontFamily: "var(--font-heading)",
  color: "var(--color-text)",
};

export default function StepPreferences({
  tempUnit,
  pressureUnit,
  windUnit,
  rainUnit,
  metarEnabled,
  metarStation,
  nwsEnabled,
  onChange,
}: StepPreferencesProps) {
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
        Choose your preferred display units and enable optional services. These
        can be changed later in Settings.
      </p>

      {/* Units */}
      <div style={cardStyle}>
        <h4 style={sectionTitle}>Units</h4>

        <div style={fieldGroup}>
          <label style={labelStyle}>Temperature</label>
          <div style={radioGroup}>
            {(["F", "C"] as const).map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="setup_temp"
                  checked={tempUnit === u}
                  onChange={() => onChange({ tempUnit: u })}
                />
                {u === "F" ? "Fahrenheit (\u00B0F)" : "Celsius (\u00B0C)"}
              </label>
            ))}
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Pressure</label>
          <div style={radioGroup}>
            {(["inHg", "hPa"] as const).map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="setup_pressure"
                  checked={pressureUnit === u}
                  onChange={() => onChange({ pressureUnit: u })}
                />
                {u === "inHg"
                  ? "Inches of Mercury (inHg)"
                  : "Hectopascals (hPa)"}
              </label>
            ))}
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Wind Speed</label>
          <div style={radioGroup}>
            {(["mph", "kph", "knots"] as const).map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="setup_wind"
                  checked={windUnit === u}
                  onChange={() => onChange({ windUnit: u })}
                />
                {u === "mph"
                  ? "Miles per hour"
                  : u === "kph"
                    ? "Kilometers per hour"
                    : "Knots"}
              </label>
            ))}
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={labelStyle}>Rain</label>
          <div style={radioGroup}>
            {(["in", "mm"] as const).map((u) => (
              <label key={u} style={radioLabel}>
                <input
                  type="radio"
                  name="setup_rain"
                  checked={rainUnit === u}
                  onChange={() => onChange({ rainUnit: u })}
                />
                {u === "in" ? "Inches" : "Millimeters"}
              </label>
            ))}
          </div>
        </div>
      </div>

      {/* Services */}
      <div style={cardStyle}>
        <h4 style={sectionTitle}>Services</h4>

        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={nwsEnabled}
              onChange={(e) => onChange({ nwsEnabled: e.target.checked })}
            />
            Enable NWS forecast data
          </label>
          <div
            style={{
              fontSize: "12px",
              color: "var(--color-text-muted)",
              marginTop: "4px",
              marginLeft: "26px",
            }}
          >
            Requires a US location with valid coordinates
          </div>
        </div>

        <div style={fieldGroup}>
          <label style={checkboxLabel}>
            <input
              type="checkbox"
              checked={metarEnabled}
              onChange={(e) => onChange({ metarEnabled: e.target.checked })}
            />
            Enable METAR data
          </label>
        </div>

        {metarEnabled && (
          <div style={{ ...fieldGroup, marginLeft: "26px" }}>
            <label style={labelStyle}>METAR Station ID</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="e.g. KJFK"
              value={metarStation}
              onChange={(e) =>
                onChange({ metarStation: e.target.value.toUpperCase() })
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}

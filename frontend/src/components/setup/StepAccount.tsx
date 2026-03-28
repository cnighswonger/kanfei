/**
 * Setup wizard step: create the admin account.
 */

interface StepAccountProps {
  adminUsername: string;
  adminPassword: string;
  adminPasswordConfirm: string;
  onChange: (partial: { adminUsername?: string; adminPassword?: string; adminPasswordConfirm?: string }) => void;
}

const fieldGroup: React.CSSProperties = {
  marginBottom: "16px",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "13px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "4px",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  fontSize: "14px",
  fontFamily: "var(--font-body)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: "6px",
  boxSizing: "border-box",
};

const hintStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "var(--color-text-muted)",
  marginTop: "4px",
};

export default function StepAccount({ adminUsername, adminPassword, adminPasswordConfirm, onChange }: StepAccountProps) {
  const mismatch = adminPassword.length > 0 && adminPasswordConfirm.length > 0 && adminPassword !== adminPasswordConfirm;

  return (
    <div>
      <h2 style={{ fontSize: "18px", fontFamily: "var(--font-heading)", color: "var(--color-text)", margin: "0 0 8px 0" }}>
        Admin Account
      </h2>
      <p style={{ fontSize: "13px", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", margin: "0 0 24px 0" }}>
        Create an admin account to protect your station settings.
      </p>

      <div style={fieldGroup}>
        <label style={labelStyle}>Username</label>
        <input
          style={inputStyle}
          type="text"
          value={adminUsername}
          onChange={(e) => onChange({ adminUsername: e.target.value })}
          autoComplete="username"
          placeholder="admin"
        />
        <div style={hintStyle}>At least 3 characters</div>
      </div>

      <div style={fieldGroup}>
        <label style={labelStyle}>Password</label>
        <input
          style={inputStyle}
          type="password"
          value={adminPassword}
          onChange={(e) => onChange({ adminPassword: e.target.value })}
          autoComplete="new-password"
        />
        <div style={hintStyle}>At least 8 characters</div>
      </div>

      <div style={fieldGroup}>
        <label style={labelStyle}>Confirm Password</label>
        <input
          style={{
            ...inputStyle,
            borderColor: mismatch ? "var(--color-danger)" : "var(--color-border)",
          }}
          type="password"
          value={adminPasswordConfirm}
          onChange={(e) => onChange({ adminPasswordConfirm: e.target.value })}
          autoComplete="new-password"
        />
        {mismatch && (
          <div style={{ ...hintStyle, color: "var(--color-danger)" }}>Passwords do not match</div>
        )}
      </div>
    </div>
  );
}

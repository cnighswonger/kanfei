/**
 * Setup wizard step: create the admin account.
 */

interface StepAccountProps {
  adminUsername: string;
  adminPassword: string;
  adminPasswordConfirm: string;
  driverType: string;
  onChange: (partial: { adminUsername?: string; adminPassword?: string; adminPasswordConfirm?: string }) => void;
}

const fieldGroup: React.CSSProperties = {
  marginBottom: "16px",
};

const labelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "calc(13px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "4px",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  fontSize: "calc(14px * var(--font-scale))",
  fontFamily: "var(--font-body)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  border: "1px solid var(--color-border)",
  borderRadius: "6px",
  boxSizing: "border-box",
};

const hintStyle: React.CSSProperties = {
  fontSize: "calc(12px * var(--font-scale))",
  color: "var(--color-text-muted)",
  marginTop: "4px",
};

export default function StepAccount({ adminUsername, adminPassword, adminPasswordConfirm, driverType, onChange }: StepAccountProps) {
  const mismatch = adminPassword.length > 0 && adminPasswordConfirm.length > 0 && adminPassword !== adminPasswordConfirm;

  // Public droplet has no admin account (require_admin bypass covers
  // reads; writes are middleware-blocked).  Skip the form entirely
  // so the operator can click Finish.  Issue #336 Phase 4.
  if (driverType === "public_relay") {
    return (
      <div>
        <h2 style={{ fontSize: "calc(18px * var(--font-scale))", fontFamily: "var(--font-heading)", color: "var(--color-text)", margin: "0 0 8px 0" }}>
          Admin Account
        </h2>
        <p style={{ fontSize: "calc(13px * var(--font-scale))", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", margin: "0 0 12px 0" }}>
          Not required for a public droplet.  Click <strong>Finish Setup</strong>
          {" "}to complete.
        </p>
        <p style={hintStyle}>
          A public droplet is a read-only demo instance — every write
          endpoint is blocked at the middleware layer, so there is
          nothing for an admin account to authenticate.  If you later
          switch this instance to a real station driver, re-run the
          setup wizard and you'll be prompted to create an admin then.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 style={{ fontSize: "calc(18px * var(--font-scale))", fontFamily: "var(--font-heading)", color: "var(--color-text)", margin: "0 0 8px 0" }}>
        Admin Account
      </h2>
      <p style={{ fontSize: "calc(13px * var(--font-scale))", fontFamily: "var(--font-body)", color: "var(--color-text-secondary)", margin: "0 0 24px 0" }}>
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

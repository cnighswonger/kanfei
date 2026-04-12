/**
 * Login page — authenticates the user and redirects to the previous page.
 *
 * When no admin account exists yet (upgrade from a pre-auth beta), this page
 * detects the `setup_required` flag from /api/auth/me and shows an account
 * creation form instead, calling POST /api/auth/setup-admin.
 */

import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { fetchCurrentUser, setupAdmin } from "../api/client";

const containerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  height: "100vh",
  background: "var(--color-bg)",
};

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "32px",
  width: "100%",
  maxWidth: "380px",
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

const btnStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 16px",
  fontSize: "14px",
  fontWeight: 600,
  fontFamily: "var(--font-body)",
  background: "var(--color-accent)",
  color: "#fff",
  border: "none",
  borderRadius: "6px",
  cursor: "pointer",
};

export default function Login() {
  const { login, refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from || "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);

  // On mount, check whether we need account creation vs login.
  useEffect(() => {
    fetchCurrentUser().then((u) => {
      if (u?.setup_required) {
        setSetupRequired(true);
      } else {
        setSetupRequired(false);
      }
    }).catch(() => setSetupRequired(false));
  }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error && err.message.includes("401")
        ? "Invalid username or password"
        : "Login failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (username.length < 3) {
      setError("Username must be at least 3 characters");
      return;
    }
    setSubmitting(true);
    try {
      await setupAdmin(username, password);
      await login(username, password);
      await refresh();
      navigate(from, { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Account creation failed");
    } finally {
      setSubmitting(false);
    }
  };

  // Still checking — show nothing.
  if (setupRequired === null) return null;

  return (
    <div style={containerStyle}>
      <div style={cardStyle}>
        <h2 style={{
          margin: "0 0 4px 0",
          fontSize: "22px",
          fontFamily: "var(--font-heading)",
          color: "var(--color-text)",
          textAlign: "center",
        }}>
          Kanfei
        </h2>
        <p style={{
          margin: "0 0 24px 0",
          fontSize: "13px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-muted)",
          textAlign: "center",
        }}>
          {setupRequired
            ? "Create an admin account to continue"
            : "Sign in to continue"}
        </p>

        {setupRequired ? (
          <form onSubmit={handleCreateAccount}>
            <div style={{ marginBottom: "16px" }}>
              <label style={{
                display: "block",
                fontSize: "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                marginBottom: "4px",
              }}>
                Username
              </label>
              <input
                style={inputStyle}
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
              />
            </div>

            <div style={{ marginBottom: "16px" }}>
              <label style={{
                display: "block",
                fontSize: "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                marginBottom: "4px",
              }}>
                Password
              </label>
              <input
                style={inputStyle}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>

            <div style={{ marginBottom: "24px" }}>
              <label style={{
                display: "block",
                fontSize: "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                marginBottom: "4px",
              }}>
                Confirm Password
              </label>
              <input
                style={inputStyle}
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>

            {error && (
              <p style={{
                color: "var(--color-danger)",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                margin: "0 0 16px 0",
                textAlign: "center",
              }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              style={{ ...btnStyle, opacity: submitting ? 0.6 : 1 }}
              disabled={submitting || !username || !password || !confirmPassword}
            >
              {submitting ? "Creating account..." : "Create Account"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleLogin}>
            <div style={{ marginBottom: "16px" }}>
              <label style={{
                display: "block",
                fontSize: "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                marginBottom: "4px",
              }}>
                Username
              </label>
              <input
                style={inputStyle}
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
                autoComplete="username"
              />
            </div>

            <div style={{ marginBottom: "24px" }}>
              <label style={{
                display: "block",
                fontSize: "12px",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-secondary)",
                marginBottom: "4px",
              }}>
                Password
              </label>
              <input
                style={inputStyle}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <p style={{
                color: "var(--color-danger)",
                fontSize: "13px",
                fontFamily: "var(--font-body)",
                margin: "0 0 16px 0",
                textAlign: "center",
              }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              style={{ ...btnStyle, opacity: submitting ? 0.6 : 1 }}
              disabled={submitting || !username || !password}
            >
              {submitting ? "Signing in..." : "Sign In"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

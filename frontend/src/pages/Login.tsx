/**
 * Login page — authenticates the user and redirects to the previous page.
 */

import { useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

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
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string })?.from || "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
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
          Sign in to continue
        </p>

        <form onSubmit={handleSubmit}>
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
      </div>
    </div>
  );
}

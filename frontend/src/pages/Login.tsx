/**
 * Login page — authenticates the user and redirects to the previous page.
 *
 * When no admin account exists yet (upgrade from a pre-auth beta), this page
 * detects the `setup_required` flag from /api/auth/me and shows an account
 * creation form instead, calling POST /api/auth/setup-admin.
 *
 * Renders a per-theme hero background behind the auth card per the Design
 * Agent's Sign-in / first-run spec:
 *   - dark / light: about-hero.jpg photo at 0.30 opacity
 *   - glaisher:     the Adieu-1867 engraving with sepia+multiply
 *   - mammoth:      the Flammarion engraving with sepia+multiply
 *   - classic:      no hero, plain background (matches the theme's spartan tone)
 */

import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { fetchCurrentUser, setupAdmin } from "../api/client";

/**
 * Per-theme background for the auth screen.  Kept local to this page for
 * now; if a second screen wants the same per-theme treatment we can lift
 * this into a shared config or onto the theme shape itself.
 */
interface AuthBackground {
  image: string;
  opacity: number;
  filter?: string;
  blend?: string;
  position?: string;
}

const AUTH_BACKGROUNDS: Record<string, AuthBackground | null> = {
  dark: {
    image: "/about-hero.jpg",
    opacity: 0.30,
    position: "center 40%",
  },
  light: {
    image: "/about-hero.jpg",
    opacity: 0.30,
    position: "center 40%",
  },
  glaisher: {
    image: "/glaisher-adieu-1867.png",
    opacity: 0.5,
    filter: "sepia(0.62) contrast(1.02) saturate(0.85)",
    blend: "multiply",
    position: "center 42%",
  },
  mammoth: {
    image: "/glaisher-flammarion.png",
    opacity: 0.13,
    filter: "sepia(0.62) contrast(1.05) saturate(0.85)",
    blend: "multiply",
    position: "center 30%",
  },
  classic: null,
};

const containerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  height: "100vh",
  background: "var(--color-bg)",
  position: "relative",
  overflow: "hidden",
};

const cardStyle: React.CSSProperties = {
  background: "var(--color-bg-card)",
  borderRadius: "var(--gauge-border-radius)",
  border: "1px solid var(--color-border)",
  padding: "32px",
  width: "100%",
  maxWidth: "380px",
  position: "relative",
  zIndex: 1,
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

const btnStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 16px",
  fontSize: "calc(14px * var(--font-scale))",
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
  const { themeName } = useTheme();
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

  const bg = AUTH_BACKGROUNDS[themeName] ?? null;

  return (
    <div style={containerStyle}>
      {bg && (
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 0,
            backgroundImage: `url(${bg.image})`,
            backgroundSize: "cover",
            backgroundPosition: bg.position ?? "center",
            backgroundRepeat: "no-repeat",
            opacity: bg.opacity,
            filter: bg.filter,
            mixBlendMode: (bg.blend ?? "normal") as React.CSSProperties["mixBlendMode"],
            pointerEvents: "none",
          }}
        />
      )}

      <div style={cardStyle}>
        <h2 style={{
          margin: "0 0 4px 0",
          fontSize: "calc(22px * var(--font-scale))",
          fontFamily: "var(--font-heading)",
          color: "var(--color-text)",
          textAlign: "center",
        }}>
          Kanfei
        </h2>
        <p style={{
          margin: "0 0 8px 0",
          fontSize: "calc(13px * var(--font-scale))",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-muted)",
          textAlign: "center",
        }}>
          {setupRequired
            ? "Create an admin account to continue"
            : "Sign in to continue"}
        </p>
        {!setupRequired && (
          <p style={{
            margin: "0 0 24px 0",
            fontSize: "calc(11px * var(--font-scale))",
            fontFamily: "var(--font-body)",
            color: "var(--color-text-muted)",
            textAlign: "center",
            fontStyle: "italic",
          }}>
            Reading the dashboard doesn't require an account.
          </p>
        )}
        {setupRequired && <div style={{ marginBottom: "16px" }} />}

        {setupRequired ? (
          <form onSubmit={handleCreateAccount}>
            <div style={{ marginBottom: "16px" }}>
              <label style={{
                display: "block",
                fontSize: "calc(12px * var(--font-scale))",
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
                fontSize: "calc(12px * var(--font-scale))",
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
                fontSize: "calc(12px * var(--font-scale))",
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
                fontSize: "calc(13px * var(--font-scale))",
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
                fontSize: "calc(12px * var(--font-scale))",
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
                fontSize: "calc(12px * var(--font-scale))",
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
                fontSize: "calc(13px * var(--font-scale))",
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

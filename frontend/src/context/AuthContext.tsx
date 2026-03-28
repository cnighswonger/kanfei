/**
 * Authentication context — tracks login state and provides login/logout methods.
 *
 * Listens for `kanfei:auth-required` events dispatched by the API client
 * when a 401 response is received, triggering a redirect to the login page.
 */

import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { fetchCurrentUser, login as apiLogin, logout as apiLogout, type AuthUser } from "../api/client";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  loggingOut: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);
  const loggingOutRef = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();

  const refresh = useCallback(async () => {
    const u = await fetchCurrentUser();
    setUser(u);
    setLoading(false);
  }, []);

  // Check session on mount.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Listen for 401 events from the API client.
  useEffect(() => {
    const handler = () => {
      // Suppress redirect during intentional logout — we're already
      // navigating to the dashboard.
      if (loggingOutRef.current) return;
      setUser(null);
      if (location.pathname !== "/login") {
        navigate("/login", { replace: true });
      }
    };
    window.addEventListener("kanfei:auth-required", handler);
    return () => window.removeEventListener("kanfei:auth-required", handler);
  }, [navigate, location.pathname]);

  const login = useCallback(async (username: string, password: string) => {
    const u = await apiLogin(username, password);
    setUser({ ...u, authenticated: true });
    sessionStorage.setItem("knf_was_authed", "1");
  }, []);

  const logout = useCallback(async () => {
    loggingOutRef.current = true;
    setLoggingOut(true);
    await apiLogout();
    sessionStorage.removeItem("knf_was_authed");
    setUser(null);
    navigate("/", { replace: true });
    setTimeout(() => { loggingOutRef.current = false; setLoggingOut(false); }, 200);
  }, [navigate]);

  return (
    <AuthContext.Provider value={{ user, loading, loggingOut, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

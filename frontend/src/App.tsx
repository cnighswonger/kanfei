import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ThemeProvider } from './context/ThemeContext';
import { WeatherBackgroundProvider } from './context/WeatherBackgroundContext';
import { WeatherDataProvider, useWeatherData } from './context/WeatherDataContext';
import { AlertProvider } from './context/AlertContext';
import { FeatureFlagsProvider, useFeatureFlags } from './context/FeatureFlagsContext';
import { DashboardLayoutProvider } from './dashboard/DashboardLayoutContext';
import { AuthProvider, useAuth } from './context/AuthContext';
import AlertToast from './components/AlertToast';
import AppShell from './components/layout/AppShell';
import Dashboard from './pages/Dashboard';
import History from './pages/History';
import Forecast from './pages/Forecast';
import Astronomy from './pages/Astronomy';
import Settings from './pages/Settings';
import Nowcast from './pages/Nowcast';
import Spray from './pages/Spray';
import MapView from './pages/MapView';
import About from './pages/About';
import Login from './pages/Login';
import SetupWizard from './components/setup/SetupWizard';
import { fetchSetupStatus } from './api/client';

/** Guard that redirects to /login if not authenticated, preserving intended destination. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, loading, loggingOut } = useAuth();
  const location = useLocation();
  if (loading || loggingOut) return null;
  if (!user?.authenticated) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  return <>{children}</>;
}

function AppContent() {
  const { connected, currentConditions } = useWeatherData();
  const { flags, loading: flagsLoading } = useFeatureFlags();
  const lastUpdate = currentConditions?.timestamp
    ? new Date(currentConditions.timestamp)
    : null;

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="*" element={
        <AppShell connected={connected} lastUpdate={lastUpdate}>
          <AlertToast />
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/history" element={<History />} />
            <Route path="/forecast" element={<Forecast />} />
            <Route path="/astronomy" element={<Astronomy />} />
            <Route path="/map" element={flags.mapEnabled ? <MapView /> : flagsLoading ? null : <Navigate to="/" replace />} />
            <Route path="/nowcast" element={flags.nowcastEnabled ? <Nowcast /> : flagsLoading ? null : <Navigate to="/" replace />} />
            <Route path="/spray" element={flags.sprayEnabled ? <Spray /> : flagsLoading ? null : <Navigate to="/" replace />} />
            <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
            <Route path="/about" element={<About />} />
          </Routes>
        </AppShell>
      } />
    </Routes>
  );
}

function App() {
  const [setupChecked, setSetupChecked] = useState(false);
  const [setupComplete, setSetupComplete] = useState(false);

  useEffect(() => {
    fetchSetupStatus()
      .then((s) => {
        setSetupComplete(s.setup_complete);
        setSetupChecked(true);
      })
      .catch(() => {
        // Fail-open: if API unreachable, assume setup done to avoid lockout
        setSetupComplete(true);
        setSetupChecked(true);
      });
  }, []);

  if (!setupChecked) {
    return (
      <ThemeProvider>
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            height: "100vh",
            background: "var(--color-bg)",
          }}
        >
          <div
            style={{
              width: "36px",
              height: "36px",
              border: "3px solid var(--color-border)",
              borderTopColor: "var(--color-accent)",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }}
          />
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </ThemeProvider>
    );
  }

  if (!setupComplete) {
    return (
      <ThemeProvider>
        <SetupWizard onComplete={() => setSetupComplete(true)} />
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <WeatherBackgroundProvider>
        <BrowserRouter>
          <AuthProvider>
            <WeatherDataProvider>
              <FeatureFlagsProvider>
                <AlertProvider>
                  <DashboardLayoutProvider>
                    <AppContent />
                  </DashboardLayoutProvider>
                </AlertProvider>
              </FeatureFlagsProvider>
            </WeatherDataProvider>
          </AuthProvider>
        </BrowserRouter>
      </WeatherBackgroundProvider>
    </ThemeProvider>
  );
}

export default App;

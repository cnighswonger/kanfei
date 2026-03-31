/**
 * MapView — full-page interactive weather map with nearby stations,
 * isobar contours, and NWS alert polygons.
 */
import { useState, useEffect, useCallback } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  GeoJSON,
  // Polyline,  // re-enable for isobars
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { useTheme } from "../context/ThemeContext.tsx";
import { API_BASE } from "../utils/constants.ts";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NearbyStation {
  id: string;
  name: string;
  lat: number;
  lon: number;
  distance_mi: number | null;
  source: string;
  temp_f: number | null;
  wind_mph: number | null;
  wind_dir: number | null;
  wind_gust_mph: number | null;
  pressure_hpa: number | null;
  pressure_inhg: number | null;
  precip_in: number | null;
  updated: string | null;
}

type DisplayMode = "temp" | "wind" | "precip";

interface MapAlert {
  event: string;
  severity: string;
  headline: string;
  description: string;
  instruction: string;
  onset: string;
  expires: string;
  geometry: GeoJSON.GeoJsonObject | null;
}

interface HomeStation {
  name: string;
  lat: number;
  lon: number;
  temp_f: number | null;
  wind_mph: number | null;
  pressure_hpa: number | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function severityColor(severity: string): string {
  switch (severity) {
    case "Extreme":
      return "#ef4444";
    case "Severe":
      return "#f97316";
    case "Moderate":
      return "#eab308";
    case "Minor":
      return "#3b82f6";
    default:
      return "#9ca3af";
  }
}

function tempColor(f: number): string {
  const clamped = Math.max(40, Math.min(100, f));
  const t = (clamped - 40) / 60; // 0 = blue, 1 = red
  const r = Math.round(50 + 205 * t);
  const b = Math.round(220 - 180 * t);
  const g = Math.round(t < 0.5 ? 80 + 160 * (t * 2) : 240 - 200 * ((t - 0.5) * 2));
  return `rgb(${r},${g},${b})`;
}

function precipColor(inches: number): string {
  const t = Math.min(1, inches / 2);
  const alpha = 0.3 + 0.7 * t;
  return `rgba(59,130,246,${alpha.toFixed(2)})`;
}

// TODO: re-enable with canvas-rendered labels
// function formatValue(station: NearbyStation, mode: DisplayMode): string { ... }

function markerColor(station: NearbyStation, mode: DisplayMode): string {
  switch (mode) {
    case "temp":
      return station.temp_f != null ? tempColor(station.temp_f) : "#9ca3af";
    case "wind":
      return "#9ca3af";
    case "precip":
      return station.precip_in != null ? precipColor(station.precip_in) : "#9ca3af";
  }
}

// ---------------------------------------------------------------------------
// IDW interpolation + marching squares
// ---------------------------------------------------------------------------

// TODO: re-enable IDW interpolation for isobars
// function idwInterpolate(...) { ... }

// TODO: re-enable marching squares for isobars
// function extractContours(...) { ... }

// ---------------------------------------------------------------------------
// Mobile hook
// ---------------------------------------------------------------------------

function useIsMobile() {
  const [m, setM] = useState(window.innerWidth < 768);
  useEffect(() => {
    const h = () => setM(window.innerWidth < 768);
    window.addEventListener("resize", h);
    return () => window.removeEventListener("resize", h);
  }, []);
  return m;
}

// ---------------------------------------------------------------------------
// Theme-aware tile layer
// ---------------------------------------------------------------------------

function ThemeAwareTiles() {
  const { themeName } = useTheme();
  const url =
    themeName === "dark"
      ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";

  // Key forces react-leaflet to unmount/remount the TileLayer on theme change
  return (
    <TileLayer
      key={themeName}
      url={url}
      attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
      subdomains="abcd"
      maxZoom={19}
    />
  );
}

// ---------------------------------------------------------------------------
// Tooltip style injection
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Control panel
// ---------------------------------------------------------------------------

const MODE_LABELS: { mode: DisplayMode; label: string }[] = [
  { mode: "temp", label: "Temp" },
  { mode: "wind", label: "Wind" },
  { mode: "precip", label: "Precip" },
];

interface ControlPanelProps {
  displayMode: DisplayMode;
  setDisplayMode: (m: DisplayMode) => void;
  showAlerts: boolean;
  setShowAlerts: (v: boolean) => void;
  alertCount: number;
  isMobile: boolean;
}

function ControlPanel({
  displayMode,
  setDisplayMode,
  showAlerts,
  setShowAlerts,
  alertCount,
  isMobile,
}: ControlPanelProps) {
  const panelStyle: React.CSSProperties = isMobile
    ? {
        position: "absolute",
        bottom: 16,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1000,
        background: "var(--color-bg-card)",
        border: "1px solid var(--color-border)",
        borderRadius: "20px",
        padding: "4px 8px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        display: "flex",
        alignItems: "center",
        gap: "4px",
      }
    : {
        position: "absolute",
        top: 12,
        right: 12,
        zIndex: 1000,
        background: "var(--color-bg-card)",
        border: "1px solid var(--color-border)",
        borderRadius: "8px",
        padding: "6px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
      };

  const btnRow: React.CSSProperties = {
    display: "flex",
    gap: "2px",
  };

  const btnBase: React.CSSProperties = {
    border: "none",
    borderRadius: "4px",
    padding: isMobile ? "4px 10px" : "4px 12px",
    fontSize: "12px",
    fontWeight: 600,
    cursor: "pointer",
    transition: "background 0.15s, color 0.15s",
  };

  const alertRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    fontSize: "11px",
    color: "var(--color-text-muted)",
    padding: isMobile ? "0 4px" : "0 2px",
  };

  return (
    <div style={panelStyle}>
      <div style={btnRow}>
        {MODE_LABELS.map(({ mode, label }) => (
          <button
            key={mode}
            onClick={() => setDisplayMode(mode)}
            style={{
              ...btnBase,
              background:
                displayMode === mode
                  ? "var(--color-accent)"
                  : "var(--color-bg-secondary)",
              color:
                displayMode === mode
                  ? "#fff"
                  : "var(--color-text-muted)",
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <label style={alertRow}>
        <input
          type="checkbox"
          checked={showAlerts}
          onChange={(e) => setShowAlerts(e.target.checked)}
          style={{ margin: 0 }}
        />
        Alerts{alertCount > 0 ? ` (${alertCount})` : ""}
      </label>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline fetch helpers
// ---------------------------------------------------------------------------

async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const containerStyle: React.CSSProperties = {
  flex: 1,
  position: "relative",
  overflow: "hidden",
  zIndex: 1,
};

const spinnerStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "center",
  alignItems: "center",
  flex: 1,
  color: "var(--color-text-muted)",
  fontSize: "14px",
};

export default function MapView() {
  // const { themeName } = useTheme();  // re-enable for isobars
  const isMobile = useIsMobile();

  // --- state ---
  const [home, setHome] = useState<HomeStation | null>(null);
  const [stations, setStations] = useState<NearbyStation[]>([]);
  const [alerts, setAlerts] = useState<MapAlert[]>([]);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("temp");
  const [showAlerts, setShowAlerts] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // --- data fetchers ---
  const fetchHome = useCallback(async () => {
    try {
      const data = await apiFetch<{
        station: {
          name: string;
          latitude: number | null;
          longitude: number | null;
        };
        current: Record<string, unknown>;
      }>("/api/public/weather");

      if (data.station.latitude == null || data.station.longitude == null) {
        setError("Station location not configured.");
        setLoading(false);
        return null;
      }

      const current = data.current as {
        temperature?: { outside?: { value?: number } };
        wind?: { speed?: { value?: number } };
        barometer?: { value?: number };
      };

      const hs: HomeStation = {
        name: data.station.name,
        lat: data.station.latitude,
        lon: data.station.longitude,
        temp_f: current.temperature?.outside?.value ?? null,
        wind_mph: current.wind?.speed?.value ?? null,
        pressure_hpa: current.barometer?.value ?? null,
      };
      setHome(hs);
      return hs;
    } catch {
      setError("Failed to load station data.");
      setLoading(false);
      return null;
    }
  }, []);

  const fetchStations = useCallback(async () => {
    try {
      const data = await apiFetch<{ stations: NearbyStation[] }>(
        "/api/map/nearby-stations?radius_mi=50",
      );
      setStations(data.stations);
    } catch {
      // Non-critical — keep existing data
    }
  }, []);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await apiFetch<{ alerts: MapAlert[] }>("/api/map/alerts");
      setAlerts(data.alerts);
    } catch {
      // Non-critical
    }
  }, []);

  // --- initial load ---
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const hs = await fetchHome();
      if (cancelled) return;
      if (hs) {
        await Promise.all([fetchStations(), fetchAlerts()]);
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchHome, fetchStations, fetchAlerts]);

  // --- auto-refresh ---
  useEffect(() => {
    if (!home) return;
    const stationInterval = setInterval(fetchStations, 5 * 60 * 1000);
    const alertInterval = setInterval(fetchAlerts, 2 * 60 * 1000);
    return () => {
      clearInterval(stationInterval);
      clearInterval(alertInterval);
    };
  }, [home, fetchStations, fetchAlerts]);

  // --- isobars (TODO: re-enable with performance optimization) ---

  // --- render ---

  if (loading) {
    return <div style={spinnerStyle}>Loading map data...</div>;
  }

  if (error || !home) {
    return (
      <div style={spinnerStyle}>
        {error || "Station location is not configured. Set latitude and longitude in Settings."}
      </div>
    );
  }

  // const isobarColor =
  //   themeName === "dark" ? "rgba(200,200,200,0.3)" : "rgba(100,100,100,0.3)";

  return (
    <div style={containerStyle}>

      <MapContainer
        center={[home.lat, home.lon]}
        zoom={9}
        style={{ height: "100%", width: "100%" }}
        zoomControl={!isMobile}
      >
        <ThemeAwareTiles />

        {/* Home station marker */}
        <CircleMarker
          center={[home.lat, home.lon]}
          radius={10}
          pathOptions={{
            color: "#fff",
            weight: 2,
            fillColor: "var(--color-accent)",
            fillOpacity: 0.9,
          }}
        >
          <Popup>
            <div style={{ fontSize: 13 }}>
              <strong>{home.name}</strong>
              {home.temp_f != null && <div>Temp: {Math.round(home.temp_f)}°F</div>}
              {home.wind_mph != null && <div>Wind: {Math.round(home.wind_mph)} mph</div>}
              {home.pressure_hpa != null && (
                <div>Pressure: {home.pressure_hpa.toFixed(1)} hPa</div>
              )}
            </div>
          </Popup>
        </CircleMarker>

        {/* Nearby station markers (capped at 100 nearest) */}
        {stations.slice(0, 100).map((s) => (
          <CircleMarker
            key={s.id}
            center={[s.lat, s.lon]}
            radius={5}
            pathOptions={{
              color: markerColor(s, displayMode),
              weight: 1,
              fillColor: markerColor(s, displayMode),
              fillOpacity: 0.8,
            }}
          >
            <Popup>
              <div style={{ fontSize: 12, maxWidth: 220 }}>
                <strong>{s.name}</strong>
                <div style={{ color: "#888", fontSize: 11 }}>
                  {s.source}{s.distance_mi != null ? ` \u00B7 ${s.distance_mi.toFixed(1)} mi` : ""}
                </div>
                {s.temp_f != null && <div>Temp: {Math.round(s.temp_f)}°F</div>}
                {s.wind_mph != null && (
                  <div>
                    Wind: {Math.round(s.wind_mph)} mph
                    {s.wind_gust_mph != null && ` (G${Math.round(s.wind_gust_mph)})`}
                  </div>
                )}
                {s.pressure_inhg != null && (
                  <div>Pressure: {s.pressure_inhg.toFixed(2)} inHg</div>
                )}
                {s.precip_in != null && <div>Precip: {s.precip_in.toFixed(2)}"</div>}
                {s.updated && (
                  <div style={{ color: "#888", fontSize: 10, marginTop: 2 }}>
                    Updated: {new Date(s.updated).toLocaleTimeString()}
                  </div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {/* Isobar contours — disabled pending performance optimization */}

        {/* NWS alert polygons */}
        {showAlerts &&
          alerts
            .filter((a) => a.geometry)
            .map((alert, i) => (
              <GeoJSON
                key={`alert-${i}-${alert.event}`}
                data={alert.geometry!}
                style={() => ({
                  color: severityColor(alert.severity),
                  fillColor: severityColor(alert.severity),
                  fillOpacity: 0.15,
                  weight: 2,
                })}
              >
                <Popup>
                  <div style={{ maxWidth: 300 }}>
                    <strong>{alert.event}</strong>
                    <p style={{ fontSize: 12, margin: "4px 0" }}>{alert.headline}</p>
                  </div>
                </Popup>
              </GeoJSON>
            ))}
      </MapContainer>

      {/* Floating control panel */}
      <ControlPanel
        displayMode={displayMode}
        setDisplayMode={setDisplayMode}
        showAlerts={showAlerts}
        setShowAlerts={setShowAlerts}
        alertCount={alerts.length}
        isMobile={isMobile}
      />
    </div>
  );
}

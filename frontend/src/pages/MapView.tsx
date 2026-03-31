/**
 * MapView — full-page interactive weather map with nearby stations,
 * isobar contours, and NWS alert polygons.
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import {
  MapContainer,
  CircleMarker,
  Popup,
  GeoJSON,
  Polyline,
  Tooltip,
  useMap,
} from "react-leaflet";
import L from "leaflet";
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
  distance_mi: number;
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

function formatValue(station: NearbyStation, mode: DisplayMode): string {
  switch (mode) {
    case "temp":
      return station.temp_f != null ? `${Math.round(station.temp_f)}°` : "--";
    case "wind":
      return station.wind_mph != null ? `${Math.round(station.wind_mph)}` : "--";
    case "precip":
      return station.precip_in != null ? `${station.precip_in.toFixed(2)}"` : "--";
  }
}

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

function idwInterpolate(
  points: { lat: number; lon: number; value: number }[],
  targetLat: number,
  targetLon: number,
  power: number = 2,
): number {
  let weightSum = 0;
  let valueSum = 0;
  for (const p of points) {
    const d = Math.sqrt((p.lat - targetLat) ** 2 + (p.lon - targetLon) ** 2);
    if (d < 0.001) return p.value;
    const w = 1 / d ** power;
    weightSum += w;
    valueSum += w * p.value;
  }
  return valueSum / weightSum;
}

function extractContours(
  grid: number[][],
  rows: number,
  cols: number,
  latMin: number,
  latMax: number,
  lonMin: number,
  lonMax: number,
  level: number,
): [number, number][][] {
  const segments: [number, number][][] = [];
  const dLat = (latMax - latMin) / (rows - 1);
  const dLon = (lonMax - lonMin) / (cols - 1);

  for (let r = 0; r < rows - 1; r++) {
    for (let c = 0; c < cols - 1; c++) {
      const tl = grid[r][c];
      const tr = grid[r][c + 1];
      const bl = grid[r + 1][c];
      const br = grid[r + 1][c + 1];

      const latT = latMin + r * dLat;
      const latB = latMin + (r + 1) * dLat;
      const lonL = lonMin + c * dLon;
      const lonR = lonMin + (c + 1) * dLon;

      const code =
        (tl >= level ? 8 : 0) |
        (tr >= level ? 4 : 0) |
        (br >= level ? 2 : 0) |
        (bl >= level ? 1 : 0);

      if (code === 0 || code === 15) continue;

      const lerp = (v1: number, v2: number, p1: number, p2: number) => {
        const t = (level - v1) / (v2 - v1);
        return p1 + t * (p2 - p1);
      };

      const top: [number, number] = [latT, lerp(tl, tr, lonL, lonR)];
      const right: [number, number] = [lerp(tr, br, latT, latB), lonR];
      const bottom: [number, number] = [latB, lerp(bl, br, lonL, lonR)];
      const left: [number, number] = [lerp(tl, bl, latT, latB), lonL];

      const cases: Record<number, [number, number][][]> = {
        1: [[left, bottom]],
        2: [[bottom, right]],
        3: [[left, right]],
        4: [[top, right]],
        5: [[top, right], [left, bottom]],
        6: [[top, bottom]],
        7: [[top, left]],
        8: [[top, left]],
        9: [[top, bottom]],
        10: [[top, left], [bottom, right]],
        11: [[top, right]],
        12: [[left, right]],
        13: [[bottom, right]],
        14: [[left, bottom]],
      };

      const segs = cases[code];
      if (segs) segments.push(...segs);
    }
  }

  return segments;
}

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
  const map = useMap();
  const { themeName } = useTheme();

  useEffect(() => {
    const url =
      themeName === "dark"
        ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png";

    const layer = L.tileLayer(url, {
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    });

    layer.addTo(map);

    return () => {
      map.removeLayer(layer);
    };
  }, [themeName, map]);

  return null;
}

// ---------------------------------------------------------------------------
// Tooltip style injection
// ---------------------------------------------------------------------------

function TooltipStyles() {
  return (
    <style>{`
      .station-label {
        background: none !important;
        border: none !important;
        box-shadow: none !important;
        font-size: 11px;
        font-weight: 600;
        font-family: var(--font-gauge);
        color: var(--color-text);
        padding: 0 !important;
        white-space: nowrap;
      }
      .station-label::before {
        display: none !important;
      }
    `}</style>
  );
}

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
  const { themeName } = useTheme();
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

  // --- isobars ---
  const isobars = useMemo(() => {
    if (!home) return [];

    const pressurePoints: { lat: number; lon: number; value: number }[] = stations
      .filter((s) => s.pressure_hpa != null)
      .map((s) => ({ lat: s.lat, lon: s.lon, value: s.pressure_hpa! }));

    if (home.pressure_hpa != null) {
      pressurePoints.push({
        lat: home.lat,
        lon: home.lon,
        value: home.pressure_hpa,
      });
    }

    if (pressurePoints.length < 5) return [];

    const GRID = 50;
    const latMin = home.lat - 1.5;
    const latMax = home.lat + 1.5;
    const lonMin = home.lon - 2;
    const lonMax = home.lon + 2;

    const grid: number[][] = [];
    for (let r = 0; r < GRID; r++) {
      const row: number[] = [];
      const lat = latMin + (r / (GRID - 1)) * (latMax - latMin);
      for (let c = 0; c < GRID; c++) {
        const lon = lonMin + (c / (GRID - 1)) * (lonMax - lonMin);
        row.push(idwInterpolate(pressurePoints, lat, lon));
      }
      grid.push(row);
    }

    const allValues = pressurePoints.map((p) => p.value);
    const minP = Math.min(...allValues);
    const maxP = Math.max(...allValues);
    const startLevel = Math.floor(minP / 4) * 4;
    const endLevel = Math.ceil(maxP / 4) * 4;

    const contours: { level: number; segments: [number, number][][] }[] = [];
    for (let level = startLevel; level <= endLevel; level += 4) {
      const segments = extractContours(
        grid,
        GRID,
        GRID,
        latMin,
        latMax,
        lonMin,
        lonMax,
        level,
      );
      if (segments.length > 0) {
        contours.push({ level, segments });
      }
    }

    return contours;
  }, [stations, home]);

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

  const isobarColor =
    themeName === "dark" ? "rgba(200,200,200,0.3)" : "rgba(100,100,100,0.3)";

  return (
    <div style={containerStyle}>
      <TooltipStyles />

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
          <Tooltip permanent direction="right" className="station-label">
            {home.name}
          </Tooltip>
        </CircleMarker>

        {/* Nearby station markers */}
        {stations.map((s) => (
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
                  {s.source} &middot; {s.distance_mi.toFixed(1)} mi
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
            <Tooltip permanent direction="right" className="station-label">
              {formatValue(s, displayMode)}
            </Tooltip>
          </CircleMarker>
        ))}

        {/* Isobar contours */}
        {isobars.map((iso) =>
          iso.segments.map((seg, i) => (
            <Polyline
              key={`iso-${iso.level}-${i}`}
              positions={seg}
              pathOptions={{
                color: isobarColor,
                weight: 1,
                dashArray: "4 4",
              }}
            />
          )),
        )}

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

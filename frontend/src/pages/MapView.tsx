/**
 * MapView — full-page interactive weather map with nearby stations,
 * isobar contours, and NWS alert polygons.
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Marker,
  Popup,
  GeoJSON,
  LayersControl,
  Polyline,
  useMapEvents,
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
  // Vivid blue → green → yellow → orange → red gradient
  const t = Math.max(0, Math.min(1, (f - 30) / 70)); // 30°F=0, 100°F=1
  if (t < 0.25) {
    // Blue → Cyan
    const s = t / 0.25;
    return `rgb(${Math.round(30 + 20 * s)},${Math.round(100 + 155 * s)},${Math.round(255 - 20 * s)})`;
  } else if (t < 0.45) {
    // Cyan → Green-Yellow
    const s = (t - 0.25) / 0.2;
    return `rgb(${Math.round(50 + 150 * s)},${Math.round(200 + 30 * s)},${Math.round(60 - 40 * s)})`;
  } else if (t < 0.65) {
    // Yellow → Orange
    const s = (t - 0.45) / 0.2;
    return `rgb(${Math.round(240 + 15 * s)},${Math.round(190 - 70 * s)},${Math.round(20)})`;
  } else {
    // Orange → Red
    const s = (t - 0.65) / 0.35;
    return `rgb(${Math.round(255 - 30 * s)},${Math.round(120 - 90 * s)},${Math.round(20 + 10 * s)})`;
  }
}

function precipColor(inches: number): string {
  const t = Math.min(1, inches / 1);
  return `rgb(${Math.round(30 + 30 * t)},${Math.round(140 + 60 * t)},${Math.round(220 + 35 * t)})`;
}

function windColor(mph: number): string {
  const t = Math.max(0, Math.min(1, mph / 30)); // 0mph=calm, 30mph=strong
  if (t < 0.3) return `rgb(100,${Math.round(180 + 50 * (t / 0.3))},100)`; // green
  if (t < 0.6) { const s = (t - 0.3) / 0.3; return `rgb(${Math.round(100 + 155 * s)},${Math.round(230 - 40 * s)},${Math.round(50)})`;} // yellow-orange
  const s = (t - 0.6) / 0.4; return `rgb(${Math.round(255 - 20 * s)},${Math.round(80 - 50 * s)},${Math.round(30)})`;  // red
}

function formatValue(station: NearbyStation, mode: DisplayMode): string {
  switch (mode) {
    case "temp":
      return station.temp_f != null ? `${Math.round(station.temp_f)}°` : "";
    case "wind":
      return station.wind_mph != null ? `${Math.round(station.wind_mph)}` : "";
    case "precip":
      return station.precip_in != null && station.precip_in > 0
        ? `${station.precip_in.toFixed(1)}"` : "";
  }
}

function markerColor(station: NearbyStation, mode: DisplayMode): string {
  switch (mode) {
    case "temp":
      return station.temp_f != null ? tempColor(station.temp_f) : "#9ca3af";
    case "wind":
      return station.wind_mph != null ? windColor(station.wind_mph) : "#9ca3af";
    case "precip":
      return station.precip_in != null ? precipColor(station.precip_in) : "#9ca3af";
  }
}

// ---------------------------------------------------------------------------
// IDW interpolation + marching squares
// ---------------------------------------------------------------------------


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
// Zoom-to-radius mapping for dynamic station density
// ---------------------------------------------------------------------------

function radiusForZoom(zoom: number, maxRadius: number): { radius: number; maxStations: number } {
  if (zoom <= 8) return { radius: maxRadius, maxStations: 80 };
  if (zoom <= 10) return { radius: Math.min(150, maxRadius), maxStations: 80 };
  if (zoom <= 12) return { radius: Math.min(50, maxRadius), maxStations: 120 };
  return { radius: Math.min(30, maxRadius), maxStations: 200 };
}

function ZoomHandler({ onZoomEnd }: { onZoomEnd: (zoom: number) => void }) {
  useMapEvents({
    zoomend(e) {
      onZoomEnd(e.target.getZoom());
    },
  });
  return null;
}

// ---------------------------------------------------------------------------
// Theme-aware tile layer
// ---------------------------------------------------------------------------

const TILE_CARTO_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>';
const TILE_OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const TILE_ESRI_ATTR = 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics';
const TILE_TOPO_ATTR = '&copy; <a href="https://opentopomap.org">OpenTopoMap</a> &copy; OSM';

const TILE_IEM_ATTR = 'Radar: <a href="https://mesonet.agron.iastate.edu/">IEM</a>';

function BaseLayers({ defaultLayer, radarTs }: { defaultLayer: string; radarTs: number }) {
  const { themeName } = useTheme();
  const defaultMap = themeName === "dark"
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png";

  return (
    <LayersControl position="topright">
      <LayersControl.BaseLayer checked={defaultLayer === "Map"} name="Map">
        <TileLayer key={`map-${themeName}`} url={defaultMap} attribution={TILE_CARTO_ATTR} subdomains="abcd" maxZoom={19} />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer checked={defaultLayer === "Roads"} name="Roads">
        <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={TILE_OSM_ATTR} maxZoom={19} />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer checked={defaultLayer === "Satellite"} name="Satellite">
        <TileLayer url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}" attribution={TILE_ESRI_ATTR} maxZoom={19} />
      </LayersControl.BaseLayer>
      <LayersControl.BaseLayer checked={defaultLayer === "Terrain"} name="Terrain">
        <TileLayer url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png" attribution={TILE_TOPO_ATTR} maxZoom={17} />
      </LayersControl.BaseLayer>
      <LayersControl.Overlay name="Radar">
        <TileLayer
          key={`radar-${radarTs}`}
          url={`https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q/{z}/{x}/{y}.png?_=${radarTs}`}
          attribution={TILE_IEM_ATTR}
          opacity={0.6}
          maxZoom={19}
        />
      </LayersControl.Overlay>
    </LayersControl>
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
  showIsobars: boolean;
  setShowIsobars: (v: boolean) => void;
  alertCount: number;
  isMobile: boolean;
}

function ControlPanel({
  displayMode,
  setDisplayMode,
  showAlerts,
  setShowAlerts,
  showIsobars,
  setShowIsobars,
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
        left: 60,
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
        <input type="checkbox" checked={showAlerts}
          onChange={(e) => setShowAlerts(e.target.checked)} style={{ margin: 0 }} />
        Alerts{alertCount > 0 ? ` (${alertCount})` : ""}
      </label>
      <label style={alertRow}>
        <input type="checkbox" checked={showIsobars}
          onChange={(e) => setShowIsobars(e.target.checked)} style={{ margin: 0 }} />
        Isobars
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
  const isMobile = useIsMobile();
  const { themeName } = useTheme();
  const isDark = themeName === "dark";

  // --- state ---
  const [home, setHome] = useState<HomeStation | null>(null);
  const [stations, setStations] = useState<NearbyStation[]>([]);
  const [alerts, setAlerts] = useState<MapAlert[]>([]);
  const [isobars, setIsobars] = useState<{ level: number; label: string; segments: number[][][] }[]>([]);
  const [displayMode, setDisplayMode] = useState<DisplayMode>("temp");
  const [showAlerts, setShowAlerts] = useState(true);
  const [showIsobars, setShowIsobars] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(9);
  const zoomTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [mapMaxRadius, setMapMaxRadius] = useState(450);
  const [mapDefaultLayer, setMapDefaultLayer] = useState("Roads");
  const [radarTs, setRadarTs] = useState(() => Math.floor(Date.now() / 300000));

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

  const fetchStations = useCallback(async (radius?: number, maxStations?: number) => {
    const { radius: r, maxStations: ms } = radiusForZoom(zoom, mapMaxRadius);
    const rad = radius ?? r;
    const max = maxStations ?? ms;
    try {
      const data = await apiFetch<{ stations: NearbyStation[] }>(
        `/api/map/nearby-stations?radius_mi=${rad}&max_stations=${max}`,
      );
      setStations(data.stations);
    } catch {
      // Non-critical — keep existing data
    }
  }, [zoom, mapMaxRadius]);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await apiFetch<{ alerts: MapAlert[] }>("/api/map/alerts");
      setAlerts(data.alerts);
    } catch {
      // Non-critical
    }
  }, []);

  const fetchIsobars = useCallback(async () => {
    try {
      const data = await apiFetch<{ contours: { level: number; label: string; segments: number[][][] }[] }>(
        "/api/map/isobars",
      );
      setIsobars(data.contours);
    } catch {
      // Non-critical
    }
  }, []);

  // --- initial load (show map as soon as home station is ready) ---
  useEffect(() => {
    let cancelled = false;
    (async () => {
      // Fetch map settings from config
      try {
        const cfgItems = await apiFetch<{ key: string; value: string | number | boolean }[]>("/api/config");
        if (!cancelled) {
          for (const item of cfgItems) {
            if (item.key === "map_max_radius") setMapMaxRadius(Number(item.value) || 450);
            if (item.key === "map_default_layer") setMapDefaultLayer(String(item.value) || "Roads");
          }
        }
      } catch {
        // Non-critical — use defaults
      }
      const hs = await fetchHome();
      if (cancelled) return;
      if (hs) setLoading(false);
      // Fetch stations, alerts in background; isobars after stations are cached
      fetchAlerts();
      await fetchStations();
      fetchIsobars();
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchHome, fetchStations, fetchAlerts, fetchIsobars]);

  // --- zoom change handler (debounced) ---
  const handleZoomEnd = useCallback((newZoom: number) => {
    setZoom(newZoom);
    clearTimeout(zoomTimerRef.current);
    zoomTimerRef.current = setTimeout(async () => {
      const { radius, maxStations } = radiusForZoom(newZoom, mapMaxRadius);
      await fetchStations(radius, maxStations);
      fetchIsobars();
    }, 500);
  }, [fetchStations, fetchIsobars]);

  // --- auto-refresh ---
  useEffect(() => {
    if (!home) return;
    const stationInterval = setInterval(async () => {
      await fetchStations();
      fetchIsobars();  // isobars depend on station cache — refresh right after
    }, 5 * 60 * 1000);
    const alertInterval = setInterval(fetchAlerts, 2 * 60 * 1000);
    // Radar tiles: bump cache-buster every 5 min to force re-fetch
    const radarInterval = setInterval(() => {
      setRadarTs(Math.floor(Date.now() / 300000));
    }, 5 * 60 * 1000);
    return () => {
      clearInterval(stationInterval);
      clearInterval(alertInterval);
      clearInterval(radarInterval);
    };
  }, [home, fetchStations, fetchAlerts, fetchIsobars]);


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


  return (
    <div style={containerStyle}>
      <style>{`
        .leaflet-control-layers {
          background: var(--color-bg-card) !important;
          border: 1px solid var(--color-border) !important;
          border-radius: 8px !important;
          color: var(--color-text) !important;
          box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
        }
        .leaflet-control-layers label { color: var(--color-text) !important; }
        .leaflet-control-layers-separator { border-color: var(--color-border) !important; }
        .leaflet-popup-content-wrapper {
          background: var(--color-bg-card) !important;
          color: var(--color-text) !important;
          border: 1px solid var(--color-border) !important;
          border-radius: 8px !important;
        }
        .leaflet-popup-tip { background: var(--color-bg-card) !important; }
        .leaflet-popup-close-button { color: var(--color-text-muted) !important; }
      `}</style>

      <MapContainer
        center={[home.lat, home.lon]}
        zoom={9}
        minZoom={7}
        preferCanvas={true}
        style={{ height: "100%", width: "100%" }}
        zoomControl={!isMobile}
      >
        <BaseLayers defaultLayer={mapDefaultLayer} radarTs={radarTs} />
        <ZoomHandler onZoomEnd={handleZoomEnd} />

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

        {/* Nearby station labels (capped at 100 nearest) */}
        {stations.map((s) => {
          const label = formatValue(s, displayMode);
          if (!label) return null;
          const color = markerColor(s, displayMode);
          const icon = L.divIcon({
            className: "",
            html: `<div style="
              font-size:11px;font-weight:700;font-family:var(--font-gauge);
              color:#fff;background:${color};
              padding:1px 3px;border-radius:3px;display:inline-block;
              white-space:nowrap;pointer-events:auto;
              box-shadow:0 1px 3px rgba(0,0,0,0.4);
              line-height:16px;text-align:center;
            ">${label}</div>`,
            iconSize: [0, 0],
            iconAnchor: [0, 8],
          });
          return (
            <Marker key={s.id} position={[s.lat, s.lon]} icon={icon}>
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
            </Marker>
          );
        })}

        {/* Isobar contours (server-computed) */}
        {showIsobars && isobars.map((iso) => {
          // Label every 2nd hPa level to avoid crowding; skip small contours
          const showLabel = iso.level % 2 === 0 && iso.segments.length >= 10;
          const labelIdx = Math.floor(iso.segments.length / 2);
          const labelSeg = iso.segments[labelIdx];
          const labelPt = showLabel && labelSeg
            ? labelSeg[Math.floor(labelSeg.length / 2)]
            : null;

          return (
            <React.Fragment key={`iso-group-${iso.level}`}>
              {/* Halo outline for contrast on any background */}
              {iso.segments.map((seg, i) => (
                <Polyline
                  key={`iso-halo-${iso.level}-${i}`}
                  positions={seg as [number, number][]}
                  pathOptions={{
                    color: isDark ? "rgba(0,0,0,0.4)" : "rgba(255,255,255,0.7)",
                    weight: isDark ? 4 : 5,
                    dashArray: "8 5",
                    lineCap: "round",
                  }}
                />
              ))}
              {iso.segments.map((seg, i) => (
                <Polyline
                  key={`iso-${iso.level}-${i}`}
                  positions={seg as [number, number][]}
                  pathOptions={{
                    color: isDark ? "rgba(180,210,255,0.8)" : "rgba(20,40,140,0.85)",
                    weight: isDark ? 1.5 : 2,
                    dashArray: "8 5",
                  }}
                />
              ))}
              {labelPt && (
                <Marker
                  position={labelPt as [number, number]}
                  interactive={false}
                  icon={L.divIcon({
                    className: "",
                    html: `<span style="font-size:10px;font-weight:600;color:${isDark ? "#c8dcff" : "#14287a"};background:${isDark ? "rgba(0,0,0,0.6)" : "rgba(255,255,255,0.85)"};padding:1px 4px;border-radius:2px;white-space:nowrap;text-shadow:${isDark ? "0 0 3px rgba(0,0,0,0.8)" : "0 0 3px rgba(255,255,255,0.9)"}">${iso.label}</span>`,
                    iconSize: [0, 0],
                    iconAnchor: [0, 6],
                  })}
                />
              )}
            </React.Fragment>
          );
        })}

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
        showIsobars={showIsobars}
        setShowIsobars={setShowIsobars}
        alertCount={alerts.length}
        isMobile={isMobile}
      />
    </div>
  );
}

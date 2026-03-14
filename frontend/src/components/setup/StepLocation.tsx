/**
 * Setup wizard Step 2: Location selection via interactive map.
 * Uses Leaflet + OpenStreetMap (no API key required).
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Fix default marker icons for bundlers
import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

interface StepLocationProps {
  latitude: number;
  longitude: number;
  elevation: number;
  onChange: (partial: {
    latitude?: number;
    longitude?: number;
    elevation?: number;
  }) => void;
}

const labelStyle: React.CSSProperties = {
  fontSize: "13px",
  fontFamily: "var(--font-body)",
  color: "var(--color-text-secondary)",
  marginBottom: "6px",
  display: "block",
};

const inputStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "14px",
  padding: "8px 12px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const btnStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: "13px",
  padding: "8px 16px",
  borderRadius: "6px",
  border: "1px solid var(--color-border)",
  background: "var(--color-bg-secondary)",
  color: "var(--color-text)",
  cursor: "pointer",
};

/** Pan map when external coordinates change. */
function MapUpdater({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  const prevRef = useRef({ lat, lng });
  useEffect(() => {
    if (lat !== prevRef.current.lat || lng !== prevRef.current.lng) {
      map.setView([lat, lng], map.getZoom());
      prevRef.current = { lat, lng };
    }
  }, [lat, lng, map]);
  return null;
}

/** Click-to-place marker handler. */
function ClickHandler({
  onClick,
}: {
  onClick: (lat: number, lng: number) => void;
}) {
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export default function StepLocation({
  latitude,
  longitude,
  elevation,
  onChange,
}: StepLocationProps) {
  const [search, setSearch] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [elevLoading, setElevLoading] = useState(false);

  // Default center: US center if no coords set
  const hasCoords = latitude !== 0 || longitude !== 0;
  const center: [number, number] = hasCoords
    ? [latitude, longitude]
    : [39.8, -98.5];
  const defaultZoom = hasCoords ? 12 : 4;

  // Fetch elevation when coordinates change
  const fetchElevation = useCallback(
    async (lat: number, lon: number) => {
      setElevLoading(true);
      try {
        const resp = await fetch(
          `https://api.open-meteo.com/v1/elevation?latitude=${lat}&longitude=${lon}`,
        );
        if (resp.ok) {
          const data = await resp.json();
          const meters = data.elevation?.[0];
          if (typeof meters === "number") {
            onChange({ elevation: Math.round(meters * 3.28084) });
          }
        }
      } catch {
        // Non-blocking — user can enter manually
      } finally {
        setElevLoading(false);
      }
    },
    [onChange],
  );

  const handleMapClick = useCallback(
    (lat: number, lng: number) => {
      const rlat = Math.round(lat * 10000) / 10000;
      const rlng = Math.round(lng * 10000) / 10000;
      onChange({ latitude: rlat, longitude: rlng });
      fetchElevation(rlat, rlng);
    },
    [onChange, fetchElevation],
  );

  const handleSearch = useCallback(async () => {
    if (!search.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const resp = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(search)}&limit=1`,
        { headers: { "User-Agent": "DavisWxUI/1.0" } },
      );
      const results = await resp.json();
      if (results.length > 0) {
        const lat = Math.round(parseFloat(results[0].lat) * 10000) / 10000;
        const lon = Math.round(parseFloat(results[0].lon) * 10000) / 10000;
        onChange({ latitude: lat, longitude: lon });
        fetchElevation(lat, lon);
      } else {
        setSearchError("No results found");
      }
    } catch {
      setSearchError("Search failed");
    } finally {
      setSearching(false);
    }
  }, [search, onChange, fetchElevation]);

  return (
    <div>
      <p
        style={{
          fontSize: "14px",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
          marginBottom: "16px",
          lineHeight: 1.5,
        }}
      >
        Click the map or search for an address to set your station location.
        Elevation is auto-detected from coordinates.
      </p>

      {/* Search bar */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          marginBottom: "12px",
        }}
      >
        <input
          style={{ ...inputStyle, flex: 1 }}
          type="text"
          placeholder="Search address or city..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
        />
        <button
          style={{
            ...btnStyle,
            opacity: searching ? 0.6 : 1,
            cursor: searching ? "wait" : "pointer",
            whiteSpace: "nowrap",
          }}
          onClick={handleSearch}
          disabled={searching}
        >
          {searching ? "Searching..." : "Search"}
        </button>
      </div>
      {searchError && (
        <div
          style={{
            fontSize: "12px",
            color: "var(--color-danger)",
            marginBottom: "8px",
          }}
        >
          {searchError}
        </div>
      )}

      {/* Map */}
      <div
        style={{
          borderRadius: "8px",
          overflow: "hidden",
          border: "1px solid var(--color-border)",
          marginBottom: "16px",
          height: "300px",
        }}
      >
        <MapContainer
          center={center}
          zoom={defaultZoom}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {hasCoords && <Marker position={[latitude, longitude]} />}
          <ClickHandler onClick={handleMapClick} />
          <MapUpdater lat={latitude} lng={longitude} />
        </MapContainer>
      </div>

      {/* Coordinate inputs */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "16px",
        }}
      >
        <div>
          <label style={labelStyle}>Latitude</label>
          <input
            style={inputStyle}
            type="number"
            step="0.0001"
            value={latitude || ""}
            onChange={(e) => {
              const val = parseFloat(e.target.value) || 0;
              onChange({ latitude: val });
            }}
            onBlur={() => {
              if (latitude && longitude) fetchElevation(latitude, longitude);
            }}
          />
        </div>
        <div>
          <label style={labelStyle}>Longitude</label>
          <input
            style={inputStyle}
            type="number"
            step="0.0001"
            value={longitude || ""}
            onChange={(e) => {
              const val = parseFloat(e.target.value) || 0;
              onChange({ longitude: val });
            }}
            onBlur={() => {
              if (latitude && longitude) fetchElevation(latitude, longitude);
            }}
          />
        </div>
        <div>
          <label style={labelStyle}>
            Elevation (ft) {elevLoading && "(fetching...)"}
          </label>
          <input
            style={inputStyle}
            type="number"
            step="1"
            value={elevation || ""}
            onChange={(e) =>
              onChange({ elevation: parseFloat(e.target.value) || 0 })
            }
          />
        </div>
      </div>
    </div>
  );
}

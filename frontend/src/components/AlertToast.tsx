/**
 * Fixed-position alert toast overlay. Renders active alert banners
 * below the header, stacked vertically.
 */

import { useAlerts } from "../context/AlertContext.tsx";

const SENSOR_LABELS: Record<string, string> = {
  outside_temp: "Outside temp",
  inside_temp: "Inside temp",
  wind_speed: "Wind speed",
  barometer: "Barometer",
  outside_humidity: "Humidity",
  rain_rate: "Rain rate",
};

const SENSOR_UNITS: Record<string, string> = {
  outside_temp: "\u00B0F",
  inside_temp: "\u00B0F",
  wind_speed: " mph",
  barometer: " inHg",
  outside_humidity: "%",
  rain_rate: " in/hr",
};

export default function AlertToast() {
  const { alerts, dismissAlert } = useAlerts();

  if (alerts.length === 0) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: "64px",
        right: "20px",
        zIndex: 200,
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        maxWidth: "360px",
      }}
    >
      {alerts.map((alert) => {
        const sensorLabel = SENSOR_LABELS[alert.sensor] ?? alert.sensor;
        const unit = SENSOR_UNITS[alert.sensor] ?? "";
        return (
          <div
            key={alert.id}
            style={{
              background: "var(--color-danger, #dc2626)",
              color: "#fff",
              borderRadius: "8px",
              padding: "12px 16px",
              boxShadow: "0 4px 16px rgba(0,0,0,0.3)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: "12px",
              animation: "alert-slide-in 0.3s ease",
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: "var(--font-heading)",
                  fontWeight: 600,
                  fontSize: "14px",
                  marginBottom: "4px",
                }}
              >
                {alert.label}
              </div>
              <div
                style={{
                  fontSize: "12px",
                  opacity: 0.9,
                  fontFamily: "var(--font-body)",
                }}
              >
                {sensorLabel} {alert.value}{unit} {alert.operator} {alert.threshold}{unit}
              </div>
            </div>
            <button
              onClick={() => dismissAlert(alert.id)}
              style={{
                background: "none",
                border: "none",
                color: "#fff",
                fontSize: "18px",
                cursor: "pointer",
                padding: "0 4px",
                lineHeight: 1,
                opacity: 0.7,
              }}
              aria-label="Dismiss alert"
            >
              &#x2715;
            </button>
          </div>
        );
      })}
    </div>
  );
}

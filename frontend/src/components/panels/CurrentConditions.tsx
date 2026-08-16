/**
 * Compact grid panel showing derived weather values:
 * Feels Like, Heat Index, Dew Point, Wind Chill, Theta-E.
 */
import { useWeatherData } from "../../context/WeatherDataContext.tsx";
import type { ValueWithUnit } from "../../api/types.ts";
import { useCompact } from "../../dashboard/CompactContext.tsx";

interface DerivedItem {
  label: string;
  data: ValueWithUnit | null | undefined;
}

function formatValue(item: ValueWithUnit | null | undefined): string {
  if (!item || item.value == null) return "--";
  return `${item.value.toFixed(1)} ${item.unit}`;
}

export default function CurrentConditions() {
  const { currentConditions } = useWeatherData();
  const isMobile = useCompact();

  const derived = currentConditions?.derived;

  const items: DerivedItem[] = [
    { label: "Feels Like", data: derived?.feels_like },
    { label: "Heat Index", data: derived?.heat_index },
    { label: "Dew Point", data: derived?.dew_point },
    { label: "Wind Chill", data: derived?.wind_chill },
    { label: "Theta-E", data: derived?.theta_e },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        padding: isMobile ? "8px" : "10px 14px",
        background: "var(--color-bg-card)",
        borderRadius: "var(--gauge-border-radius, 16px)",
        boxShadow: "var(--gauge-shadow, 0 4px 24px rgba(0,0,0,0.4))",
        border: "1px solid var(--color-border)",
        minWidth: "160px",
        height: "100%",
        boxSizing: "border-box",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          fontSize: "calc(12px * var(--font-scale))",
          fontFamily: "var(--font-body)",
          color: "var(--color-text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.5px",
          marginBottom: "8px",
          textAlign: "center",
        }}
      >
        Derived Conditions
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: isMobile ? "6px 8px" : "8px 16px",
        }}
      >
        {items.map((item) => (
          <div key={item.label} style={{ textAlign: "center" }}>
            <div
              style={{
                fontSize: "calc(10px * var(--font-scale))",
                fontFamily: "var(--font-body)",
                color: "var(--color-text-muted)",
                textTransform: "uppercase",
                marginBottom: "2px",
              }}
            >
              {item.label}
            </div>
            <div
              style={{
                fontSize: isMobile ? "calc(14px * var(--font-scale))" : "calc(16px * var(--font-scale))",
                fontFamily: "var(--font-gauge)",
                fontWeight: "bold",
                color: item.data
                  ? "var(--color-text)"
                  : "var(--color-text-muted)",
              }}
            >
              {formatValue(item.data)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Maps a tile ID to the corresponding gauge/panel component with
 * live weather data props. Extracted from Dashboard.tsx.
 */

import { useWeatherData } from "../context/WeatherDataContext.tsx";
import TemperatureGauge from "../components/gauges/TemperatureGauge.tsx";
import BarometerDial from "../components/gauges/BarometerDial.tsx";
import WindCompass from "../components/gauges/WindCompass.tsx";
import HumidityGauge from "../components/gauges/HumidityGauge.tsx";
import RainGauge from "../components/gauges/RainGauge.tsx";
import SolarUVGauge from "../components/gauges/SolarUVGauge.tsx";
import CurrentConditions from "../components/panels/CurrentConditions.tsx";
import StationStatus from "../components/panels/StationStatus.tsx";

interface TileRendererProps {
  tileId: string;
}

export default function TileRenderer({ tileId }: TileRendererProps) {
  const { currentConditions } = useWeatherData();
  const cc = currentConditions;

  switch (tileId) {
    case "outside-temp":
      return (
        <TemperatureGauge
          value={cc?.temperature?.outside?.value ?? null}
          unit={cc?.temperature?.outside?.unit ?? "F"}
          high={cc?.daily_extremes?.outside_temp_hi?.value ?? null}
          low={cc?.daily_extremes?.outside_temp_lo?.value ?? null}
          label="Outside"
        />
      );

    case "inside-temp":
      return (
        <TemperatureGauge
          value={cc?.temperature?.inside?.value ?? null}
          unit={cc?.temperature?.inside?.unit ?? "F"}
          high={cc?.daily_extremes?.inside_temp_hi?.value ?? null}
          low={cc?.daily_extremes?.inside_temp_lo?.value ?? null}
          label="Inside"
        />
      );

    case "barometer":
      return (
        <BarometerDial
          value={cc?.barometer?.value ?? null}
          unit={cc?.barometer?.unit ?? "inHg"}
          trend={
            cc?.barometer?.trend as
              | "rising"
              | "falling"
              | "steady"
              | null
              | undefined
          }
          trendRate={cc?.barometer?.trend_rate ?? null}
          high={cc?.daily_extremes?.barometer_hi?.value ?? null}
          low={cc?.daily_extremes?.barometer_lo?.value ?? null}
        />
      );

    case "wind":
      return (
        <WindCompass
          direction={cc?.wind?.direction?.value ?? null}
          speed={cc?.wind?.speed?.value ?? null}
          gust={cc?.wind?.gust?.value ?? null}
          peak={cc?.daily_extremes?.wind_speed_hi?.value ?? null}
          unit={cc?.wind?.speed?.unit ?? "mph"}
          cardinal={cc?.wind?.cardinal ?? null}
        />
      );

    case "outside-humidity":
      return (
        <HumidityGauge
          value={cc?.humidity?.outside?.value ?? null}
          label="Outside"
          high={cc?.daily_extremes?.humidity_hi?.value ?? null}
          low={cc?.daily_extremes?.humidity_lo?.value ?? null}
        />
      );

    case "inside-humidity":
      return (
        <HumidityGauge
          value={cc?.humidity?.inside?.value ?? null}
          label="Inside"
          high={cc?.daily_extremes?.inside_humidity_hi?.value ?? null}
          low={cc?.daily_extremes?.inside_humidity_lo?.value ?? null}
        />
      );

    case "rain":
      return (
        <RainGauge
          rate={cc?.rain?.rate?.value ?? null}
          daily={cc?.rain?.daily?.value ?? null}
          yesterday={cc?.rain?.yesterday?.value ?? null}
          yearly={cc?.rain?.yearly?.value ?? null}
          unit={cc?.rain?.daily?.unit ?? "in"}
          peakRate={(cc?.rain?.daily?.value ?? 0) > 0 ? (cc?.daily_extremes?.rain_rate_hi?.value ?? null) : null}
        />
      );

    case "solar-uv": {
      const hasSolar = cc?.solar_radiation != null;
      const hasUV = cc?.uv_index != null;
      if (!hasSolar && !hasUV) return null;
      return (
        <SolarUVGauge
          solarRadiation={cc?.solar_radiation?.value ?? null}
          uvIndex={cc?.uv_index?.value ?? null}
        />
      );
    }

    case "current-conditions":
      return <CurrentConditions />;

    case "station-status":
      return <StationStatus />;

    default:
      return null;
  }
}

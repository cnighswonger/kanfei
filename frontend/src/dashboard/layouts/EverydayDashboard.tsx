/**
 * Everyday persona — the mock, composed literally.
 *
 * Structure and every dimension in this file traces to Design's
 * TILE-CONTRACT.md: two flex columns inside a 739fr / 547fr grid,
 * per-column gaps (20 left, 18 right, 32 between), fixed tile
 * heights (not floors) because the mock heights were authored to
 * fit specific content.
 *
 * No placement data, no computation.  A tile is either here or it
 * isn't; a height is a literal or it isn't.  Reinstating drag later
 * (per FIXED-LAYOUTS.md) is slot-swap on top of this shape, not free
 * arrangement.
 */

import { useWeatherData } from "../../context/WeatherDataContext.tsx";
import HeroTemperatureTile from "../../components/tiles/HeroTemperatureTile.tsx";
import HistoryChartTile from "../../components/tiles/HistoryChartTile.tsx";
import RainHourlyTile from "../../components/tiles/RainHourlyTile.tsx";
import AlmanacTile from "../../components/tiles/AlmanacTile.tsx";
import BarometerDial from "../../components/gauges/BarometerDial.tsx";
import WindCompass from "../../components/gauges/WindCompass.tsx";
import RainGauge from "../../components/gauges/RainGauge.tsx";
import SolarUVGauge from "../../components/gauges/SolarUVGauge.tsx";
import CurrentConditions from "../../components/panels/CurrentConditions.tsx";
import StationStatus from "../../components/panels/StationStatus.tsx";
import { CompactProvider } from "../CompactContext.tsx";
import { useIsMobile } from "../../hooks/useIsMobile.ts";

const BAND_GRID: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "739fr 547fr",
  gap: 32,
};

// Every tile is a Slot: fixed height + tile-id attribute + a strict
// overflow contract so a tile that renders taller than its budget
// can't paint into the neighbouring slot (Design's fixed-height
// composition depends on the tile ending where the layout says).
function Slot({
  id,
  height,
  children,
  style,
}: {
  id: string;
  height?: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div
      data-tile-id={id}
      style={{
        height,
        minWidth: 0,
        overflow: "hidden",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

export default function EverydayDashboard() {
  const { currentConditions: cc } = useWeatherData();
  const isMobile = useIsMobile();

  return (
    <CompactProvider value={isMobile}>
    <main
      data-dashboard-grid
      style={{
        padding: "22px 28px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 20,
        minHeight: 0,
        flex: 1,
      }}
    >
      {/* Band A — hero row + chart + ledger row on the left; barometer + wind + almanac on the right */}
      <div data-band="a" style={BAND_GRID}>
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", gap: 28, height: 204 }}>
            <Slot id="outside-temp" style={{ width: 340, height: 204 }}>
              <HeroTemperatureTile />
            </Slot>
            <Slot id="current-conditions" style={{ flex: 1, height: 204 }}>
              <CurrentConditions />
            </Slot>
          </div>

          <Slot id="history-chart" height={268}>
            <HistoryChartTile />
          </Slot>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, height: 157 }}>
            <Slot id="rain" height={157}>
              <RainGauge
                rate={cc?.rain?.rate?.value ?? null}
                daily={cc?.rain?.daily?.value ?? null}
                yesterday={cc?.rain?.yesterday?.value ?? null}
                yearly={cc?.rain?.yearly?.value ?? null}
                unit={cc?.rain?.daily?.unit ?? "in"}
                peakRate={(cc?.rain?.daily?.value ?? 0) > 0 ? cc?.daily_extremes?.rain_rate_hi?.value ?? null : null}
                peakRateAt={(cc?.rain?.daily?.value ?? 0) > 0 ? cc?.daily_extremes?.rain_rate_hi?.at ?? null : null}
              />
            </Slot>
            <Slot id="solar-uv" height={157}>
              <SolarUVGauge
                solarRadiation={cc?.solar_radiation?.value ?? null}
                uvIndex={cc?.uv_index?.value ?? null}
                uvWarning={cc?.uv_warning ?? null}
                solarEnergyDaily={cc?.solar_energy_daily ?? null}
                etDaily={cc?.et_daily ?? null}
                etMonthly={cc?.et_monthly ?? null}
                etYearly={cc?.et_yearly ?? null}
              />
            </Slot>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <Slot id="barometer" height={280}>
            <BarometerDial
              value={cc?.barometer?.value ?? null}
              unit={cc?.barometer?.unit ?? "inHg"}
              trend={cc?.barometer?.trend as "rising" | "falling" | "steady" | null | undefined}
              trendRate={cc?.barometer?.trend_rate ?? null}
              high={cc?.daily_extremes?.barometer_hi?.value ?? null}
              low={cc?.daily_extremes?.barometer_lo?.value ?? null}
              highAt={cc?.daily_extremes?.barometer_hi?.at ?? null}
              lowAt={cc?.daily_extremes?.barometer_lo?.at ?? null}
            />
          </Slot>
          <Slot id="wind" height={220}>
            <WindCompass
              direction={cc?.wind?.direction?.value ?? null}
              speed={cc?.wind?.speed?.value ?? null}
              gust={cc?.wind?.gust?.value ?? null}
              peak={cc?.daily_extremes?.wind_speed_hi?.value ?? null}
              peakAt={cc?.daily_extremes?.wind_speed_hi?.at ?? null}
              unit={cc?.wind?.speed?.unit ?? "mph"}
              cardinal={cc?.wind?.cardinal ?? null}
            />
          </Slot>
          <Slot id="almanac" height={157}>
            <AlmanacTile />
          </Slot>
        </div>
      </div>

      {/* Band B — full-width bottom row: hourly rainfall + station status footer */}
      <div data-band="b" style={{ ...BAND_GRID, height: 145 }}>
        <Slot id="rainfall-hourly" height={145}>
          <RainHourlyTile />
        </Slot>
        <Slot id="station-status" height={145}>
          <StationStatus />
        </Slot>
      </div>
    </main>
    </CompactProvider>
  );
}

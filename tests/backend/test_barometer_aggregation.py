"""Multi-station barometer calibration aggregation (#298).

Ported from ``kanfei-phone-sensor`` Phase 4.7 PR-B.  The algorithm
gates on min-stations-voting and cross-station-spread; both matter
because a single anomalous METAR would otherwise silently pin the
console's persistent barometer offset to a wrong value.

Coverage split into three shapes:

- **Per-station aggregation**: multiple obs per station → single median,
  including spread, ranking by distance.
- **Gates**: min-stations, spread-threshold, min-console-samples,
  no-console-data, no-METAR-data.  Order-of-firing matters — the UI
  gets one skip_reason to render, not a set.
- **Happy path**: recommendation returns the median-of-medians and the
  signed offset both in thousandths and inHg.
"""

from datetime import datetime, timezone
from typing import Any

import pytest

from app.services.barometer_aggregation import (
    CROSS_STATION_SPREAD_THRESHOLD_HPA,
    MAX_STATION_DISTANCE_MILES,
    MIN_CONSOLE_SAMPLES,
    MIN_STATIONS,
    SKIP_CROSS_STATION_DISAGREEMENT,
    SKIP_INSUFFICIENT_CONSOLE_SAMPLES,
    SKIP_INSUFFICIENT_STATIONS,
    SKIP_NO_CONSOLE_SAMPLES,
    SKIP_NO_METAR_AVAILABLE,
    ConsoleSample,
    StationMedian,
    _aggregate_per_station,
    compute_aggregate_recommendation,
    read_console_barometer_median,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


HOME_LAT = 35.4
HOME_LON = -78.6


def _obs(icao: str, name: str, lat: float, lon: float, altimeter: str,
         obs_time: int = 1700000000) -> dict[str, Any]:
    """A single aviationweather payload element."""
    return {
        "icaoId": icao,
        "name": name,
        "lat": lat,
        "lon": lon,
        "obsTime": obs_time,
        "rawOb": f"METAR {icao} 010000Z 27010KT 10SM CLR 22/15 {altimeter}",
        "metarType": "METAR",
    }


def _console(median_hpa: float = 1013.2, n_samples: int = 90) -> ConsoleSample:
    return ConsoleSample(
        median_hpa=median_hpa,
        n_samples=n_samples,
        window_minutes=15,
        stdev_hpa=0.05,
        window_start="2026-08-11T20:00:00+00:00",
        window_end="2026-08-11T20:15:00+00:00",
    )


# ---------------------------------------------------------------------------
# Per-station aggregation
# ---------------------------------------------------------------------------


class TestAggregatePerStation:
    """One station with many obs → one median.  Empty on garbage."""

    def test_single_station_multiple_obs_medians_altimeter(self):
        # Three obs from the same station: A2990, A2992, A2994 →
        # thousandths 29900, 29920, 29940 → median 29920.
        obs = [
            _obs("KRDU", "Raleigh-Durham", 35.87, -78.78, "A2990", 1700000000),
            _obs("KRDU", "Raleigh-Durham", 35.87, -78.78, "A2992", 1700003600),
            _obs("KRDU", "Raleigh-Durham", 35.87, -78.78, "A2994", 1700007200),
        ]
        result = _aggregate_per_station(
            obs, HOME_LAT, HOME_LON, MAX_STATION_DISTANCE_MILES,
        )
        assert len(result) == 1
        m = result[0]
        assert m.station_id == "KRDU"
        assert m.n_obs == 3
        assert m.median_altimeter_thousandths_inhg == 29920
        assert m.median_altimeter_inhg == 29.920
        assert m.obs_spread_thousandths_inhg == 40  # 29940 - 29900

    def test_multiple_stations_sorted_by_distance(self):
        # Two stations at different distances: nearest first.
        obs = [
            _obs("KFAR", "Far", 34.0, -78.6, "A2990"),   # ~97 mi south
            _obs("KNEAR", "Near", 35.5, -78.7, "A2992"),  # ~7 mi north
        ]
        result = _aggregate_per_station(
            obs, HOME_LAT, HOME_LON, radius_miles=200.0,
        )
        assert [m.station_id for m in result] == ["KNEAR", "KFAR"]
        assert result[0].distance_miles < result[1].distance_miles

    def test_station_beyond_radius_excluded(self):
        # 200 mi station with a 47 mi cap → excluded.
        obs = [
            _obs("KIN", "In-range", 35.5, -78.7, "A2992"),
            _obs("KOUT", "Out-of-range", 33.0, -78.6, "A2992"),  # ≈165 mi south
        ]
        result = _aggregate_per_station(
            obs, HOME_LAT, HOME_LON, radius_miles=47.0,
        )
        assert [m.station_id for m in result] == ["KIN"]

    def test_obs_without_altimeter_group_dropped(self):
        # Station-level: one obs has no A group, the other does → keep one.
        obs = [
            {
                "icaoId": "KRDU", "name": "Raleigh-Durham",
                "lat": 35.87, "lon": -78.78, "obsTime": 1700000000,
                "rawOb": "METAR KRDU 010000Z 27010KT 10SM CLR 22/15",
                # No A-group.
                "metarType": "METAR",
            },
            _obs("KRDU", "Raleigh-Durham", 35.87, -78.78, "A2992"),
        ]
        result = _aggregate_per_station(
            obs, HOME_LAT, HOME_LON, MAX_STATION_DISTANCE_MILES,
        )
        assert len(result) == 1
        assert result[0].n_obs == 1

    def test_station_with_all_obs_dropped_excluded(self):
        obs = [
            {
                "icaoId": "KRDU", "name": "Raleigh-Durham",
                "lat": 35.87, "lon": -78.78, "obsTime": 1700000000,
                "rawOb": "METAR KRDU 010000Z 27010KT 10SM CLR 22/15",
                "metarType": "METAR",
            },
        ]
        result = _aggregate_per_station(
            obs, HOME_LAT, HOME_LON, MAX_STATION_DISTANCE_MILES,
        )
        assert result == []


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


class TestGates:
    """Every gate fires at the right threshold.  Order matters: only
    one skip_reason is reported to the UI, not a set of failing gates."""

    def _stations(self, altimeters_thousandths: list[int]) -> list[StationMedian]:
        """Build per_station_medians with the given altimeter values.

        All stations look identical apart from ID + median.  The gate
        code only reads the median field for the aggregation math.
        """
        return [
            StationMedian(
                station_id=f"K{i:03d}",
                station_name=f"Station {i}",
                distance_miles=10.0 + i,
                bearing_cardinal="N",
                n_obs=3,
                median_altimeter_thousandths_inhg=t,
                median_altimeter_inhg=round(t / 1000, 3),
                obs_spread_thousandths_inhg=10,
                newest_observed_at="2026-08-11T20:00:00+00:00",
            )
            for i, t in enumerate(altimeters_thousandths)
        ]

    def test_no_console_data(self):
        r = compute_aggregate_recommendation(None, self._stations([29920, 29930]))
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_NO_CONSOLE_SAMPLES

    def test_console_zero_samples(self):
        empty = ConsoleSample(
            median_hpa=0.0, n_samples=0, window_minutes=15, stdev_hpa=0.0,
            window_start="a", window_end="b",
        )
        r = compute_aggregate_recommendation(empty, self._stations([29920, 29930]))
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_NO_CONSOLE_SAMPLES

    def test_console_below_min_samples(self):
        thin = ConsoleSample(
            median_hpa=1013.2, n_samples=MIN_CONSOLE_SAMPLES - 1,
            window_minutes=15, stdev_hpa=0.05,
            window_start="a", window_end="b",
        )
        r = compute_aggregate_recommendation(thin, self._stations([29920, 29930]))
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_INSUFFICIENT_CONSOLE_SAMPLES

    def test_no_metar_available(self):
        r = compute_aggregate_recommendation(_console(), [])
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_NO_METAR_AVAILABLE

    def test_single_station_refuses(self):
        # P0-1: one reference cannot cross-check itself.
        r = compute_aggregate_recommendation(_console(), self._stations([29920]))
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_INSUFFICIENT_STATIONS

    def test_two_stations_within_spread_passes(self):
        # 29920, 29930 → 10 thousandths spread → ≈0.033 hPa < 0.4 threshold.
        r = compute_aggregate_recommendation(_console(), self._stations([29920, 29930]))
        assert r.recommendation.should_apply is True
        assert r.recommendation.skip_reason is None

    def test_cross_station_disagreement_holds(self):
        # 29900, 30000 → 100 thousandths ≈ 0.339 hPa still under 0.4.
        # 29900, 30100 → 200 thousandths ≈ 0.677 hPa OVER 0.4 → HOLD.
        r = compute_aggregate_recommendation(
            _console(), self._stations([29900, 30100]),
        )
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_CROSS_STATION_DISAGREEMENT

    def test_cross_station_spread_reported_as_hpa(self):
        # Even when the gate fails, the spread number is on the result
        # so the UI can render it.
        # 200 thousandths of inHg = 0.2 * 33.86389 ≈ 6.77 hPa.  This is
        # a big spread, well over the 0.4 hPa threshold.
        r = compute_aggregate_recommendation(
            _console(), self._stations([29900, 30100]),
        )
        assert r.cross_station_spread_hpa is not None
        assert 6.5 <= r.cross_station_spread_hpa <= 7.0

    def test_gate_order_console_before_station(self):
        # Console-side gate fires BEFORE the station-side gate.  So an
        # empty-console + no-METAR case reports SKIP_NO_CONSOLE_SAMPLES,
        # not SKIP_NO_METAR_AVAILABLE.  This ordering pins UI behaviour.
        r = compute_aggregate_recommendation(None, [])
        assert r.recommendation.skip_reason == SKIP_NO_CONSOLE_SAMPLES


# ---------------------------------------------------------------------------
# Happy path recommendation math
# ---------------------------------------------------------------------------


class TestRecommendationMath:
    """When both gates pass, median-of-medians and signed offset."""

    def test_median_of_medians_three_stations(self):
        # 100 thousandths of inHg ≈ 3.4 hPa, so a spread of even 40
        # thousandths is 1.35 hPa — well over the 0.4 hPa gate.  Keep
        # the station values within 10 thousandths of each other so the
        # spread gate passes.
        # 29915, 29920, 29925 → median 29920.  Spread ≈ 0.34 hPa < 0.4.
        stations = [
            StationMedian(
                station_id=f"K{i}", station_name=f"S{i}", distance_miles=10.0,
                bearing_cardinal="N", n_obs=3,
                median_altimeter_thousandths_inhg=t,
                median_altimeter_inhg=round(t / 1000, 3),
                obs_spread_thousandths_inhg=0,
                newest_observed_at="2026-08-11T20:00:00+00:00",
            )
            for i, t in enumerate([29915, 29920, 29925])
        ]
        console = _console(median_hpa=1013.2)
        r = compute_aggregate_recommendation(console, stations)
        assert r.recommendation.should_apply is True
        assert r.recommendation.median_of_medians_thousandths_inhg == 29920
        assert r.recommendation.median_of_medians_inhg == 29.920

    def test_offset_is_reference_minus_console(self):
        # Console reads high (1015 hPa ~= 29971 thousandths).
        # Reference median 29920 thousandths.
        # Offset = 29920 - 29971 = -51 (console needs to come DOWN 51
        # thousandths to agree with the reference).
        stations = [
            StationMedian(
                station_id=f"K{i}", station_name=f"S{i}", distance_miles=10.0,
                bearing_cardinal="N", n_obs=3,
                median_altimeter_thousandths_inhg=29920,
                median_altimeter_inhg=29.920,
                obs_spread_thousandths_inhg=0,
                newest_observed_at="2026-08-11T20:00:00+00:00",
            )
            for i in range(2)
        ]
        console = _console(median_hpa=1015.0)
        r = compute_aggregate_recommendation(console, stations)
        assert r.recommendation.should_apply is True
        # Sign is what matters more than exact value — reference minus
        # console, so a high console reading produces a NEGATIVE offset.
        assert r.recommendation.offset_thousandths_inhg is not None
        assert r.recommendation.offset_thousandths_inhg < 0

    def test_thresholds_snapshot_in_result(self):
        r = compute_aggregate_recommendation(
            _console(),
            [
                StationMedian(
                    station_id=f"K{i}", station_name=f"S{i}",
                    distance_miles=10.0, bearing_cardinal="N", n_obs=3,
                    median_altimeter_thousandths_inhg=29920,
                    median_altimeter_inhg=29.920,
                    obs_spread_thousandths_inhg=0,
                    newest_observed_at="2026-08-11T20:00:00+00:00",
                )
                for i in range(2)
            ],
        )
        # Every threshold that the UI needs to display gate-pass state
        # is present under a stable key.  Renaming any of these breaks
        # the frontend contract.
        assert r.thresholds["min_stations"] == MIN_STATIONS
        assert (
            r.thresholds["cross_station_spread_threshold_hpa"]
            == CROSS_STATION_SPREAD_THRESHOLD_HPA
        )
        assert "console_window_minutes" in r.thresholds
        assert "min_console_samples" in r.thresholds
        assert "max_station_distance_miles" in r.thresholds
        assert "station_window_hours" in r.thresholds


# ---------------------------------------------------------------------------
# Belt-and-braces isinstance guard on the write path (#298 non-blocking nit).
# ---------------------------------------------------------------------------


class TestBarometerCalWriteBeltAndBraces:
    """`_require_barometer_cal` must refuse a driver that claims the
    capability but is not a VantageDriver.  #298 non-blocking nit — the
    capability check is the primary gate, this is defence in depth
    against future declaration drift."""

    def _daemon(self, drv):
        from logger_main import LoggerDaemon
        d = LoggerDaemon.__new__(LoggerDaemon)
        d.driver = drv
        return d

    def test_non_vantage_declaring_barometer_cal_is_refused(self):
        from app.protocol.base import CAP_BAROMETER_CAL

        # A pretend driver that lies about its capability.
        class LiarDriver:
            @property
            def connected(self):
                return True

            @property
            def capabilities(self):
                return {CAP_BAROMETER_CAL}

            @property
            def station_name(self):
                return "Not-A-Vantage"

        daemon = self._daemon(LiarDriver())
        with pytest.raises(RuntimeError, match="not a VantageDriver"):
            daemon._require_barometer_cal()

    def test_vantage_declaring_barometer_cal_passes(self):
        from app.protocol.vantage.driver import VantageDriver

        # `connected` reads `self._connected and self.serial.is_open`, so
        # the fake serial needs is_open=True to satisfy the connection
        # gate.  Whether the wire actually works is beside the point of
        # this test — the point is the isinstance check does not refuse
        # a real VantageDriver.
        drv = VantageDriver("/dev/null", 19200)
        drv._connected = True

        class _FakeSerial:
            is_open = True

        drv.serial = _FakeSerial()
        daemon = self._daemon(drv)
        # Passes the isinstance check.  Returns the driver itself.
        assert daemon._require_barometer_cal() is drv


# ---------------------------------------------------------------------------
# Unit conversion — SensorReadingModel.barometer is TENTHS of hPa
# ---------------------------------------------------------------------------


class TestConsoleMedianUnitConversion:
    """`SensorReadingModel.barometer` is stored as integer TENTHS of hPa
    (per `poller.py`'s `round(snapshot.barometer * 10)`), not hPa.
    `read_console_barometer_median` must divide by 10 to return hPa.

    Caught in a beta smoke: the API's `console.median_hpa` came back
    as 10142 for a station reading 1014.2 hPa.  The algorithm's
    cross-station-spread gate rejected the write before the wrong offset
    reached the console, so no hardware damage — but this is exactly the
    class of bug the whole module exists to prevent.
    """

    def test_reads_tenths_of_hpa_and_returns_hpa(self):
        # An in-memory session with a couple of readings at 10142 tenths
        # (= 1014.2 hPa).  If the function is off by a factor of 10, the
        # returned median will be 10142.0 instead of 1014.2.
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models.database import Base
        from app.models.sensor_reading import SensorReadingModel

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        now = datetime.now(timezone.utc)
        for i in range(30):
            db.add(
                SensorReadingModel(
                    timestamp=now - timedelta(seconds=i * 10),
                    station_type=1,   # NOT NULL — value doesn't matter
                    barometer=10142,  # 1014.2 hPa in tenths
                )
            )
        db.commit()

        result = read_console_barometer_median(db)
        assert result is not None
        # If the unit conversion is missing, this comes back at ~10142.
        # If it is right, ~1014.2.
        assert 1013.0 <= result.median_hpa <= 1015.0, (
            f"expected ~1014.2 hPa, got {result.median_hpa} — "
            "SensorReadingModel.barometer is stored in tenths and the "
            "aggregation must divide by 10"
        )
        assert result.n_samples == 30

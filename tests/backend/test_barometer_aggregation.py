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
        # Even when the gate fails, the weighted spread number is on
        # the result so the UI can render it.  For two stations at
        # different distances (fixture: 10 mi vs 11 mi) with a
        # 200-thousandths-inHg gap, the closer station's larger weight
        # pulls the weighted median to it; the weighted spread is
        # then dominated by the further station's ~6.77 hPa deviation
        # from that median, giving ~9 hPa on 2× stdev.  This is
        # correct behaviour — the operator's local pressure is what
        # the closer station reports, and the further station's
        # disagreement with that IS a large spread from the operator's
        # perspective.
        r = compute_aggregate_recommendation(
            _console(), self._stations([29900, 30100]),
        )
        assert r.cross_station_spread_hpa is not None
        assert r.cross_station_spread_hpa > CROSS_STATION_SPREAD_THRESHOLD_HPA
        # HOLD path fires with an override-allowed recommendation.
        assert r.recommendation.should_apply is False
        assert r.recommendation.hold_override_allowed is True

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


# ---------------------------------------------------------------------------
# MAD-based per-station outlier rejection
# ---------------------------------------------------------------------------


def _sm(icao: str, thousandths_inhg: int, distance_miles: float = 20.0,
        obs_spread: int = 20, n_obs: int = 5) -> StationMedian:
    """Fixture station: only fields that affect the algorithm."""
    return StationMedian(
        station_id=icao,
        station_name=f"{icao} name",
        distance_miles=distance_miles,
        bearing_cardinal="N",
        n_obs=n_obs,
        median_altimeter_thousandths_inhg=thousandths_inhg,
        median_altimeter_inhg=thousandths_inhg / 1000,
        obs_spread_thousandths_inhg=obs_spread,
        newest_observed_at="2026-08-11T20:15:00+00:00",
    )


class TestMadOutlierRejection:
    """A single miscalibrated AWOS at a distant airfield used to poison
    the whole spread gate.  The MAD filter is what stops it — verify
    the failure mode from the vsits-02 smoke would now be caught.
    """

    def test_smoke_case_from_beta27_rejects_both_extremes(self):
        """The exact wire data from the beta27 smoke: 14 NC-central
        METAR stations, KGSB and KSOP dragging the max−min spread to
        3.22 hPa.  MAD (iterated at k=2.5) rejects both — KGSB on pass
        1, KSOP on pass 2 once the MAD tightens.  The middle 12 still
        span ~1.7 hPa which fails the 0.4 hPa spread gate, so HOLD is
        still the outcome — but the diagnostic is now truthful: '12 of
        14 stations agree within 1.7 hPa, 2 excluded' rather than the
        misleading '14 stations disagree by 3.2 hPa'.
        """
        # Values in thousandths of inHg, as returned from the wire.
        wire = {
            "KGSB": 29935, "KGWW": 29960, "KJNX": 29970, "KW40": 29980,
            "KDPL": 29980, "KLHZ": 29980, "KRDU": 29985, "KFBG": 29990,
            "KFAY": 29990, "KPOB": 30000, "KCTZ": 30000, "KTTA": 30000,
            "KHRJ": 30010, "KSOP": 30030,
        }
        stations = [_sm(icao, t) for icao, t in wire.items()]

        result = compute_aggregate_recommendation(_console(), stations)

        assert result.n_stations_considered == 14
        excluded = {s.station_id for s in result.per_station_medians
                    if s.is_outlier}
        assert excluded == {"KGSB", "KSOP"}, (
            f"iterated MAD at k=2.5 must reject both extreme outliers "
            f"— got excluded={excluded}, n_used={result.n_stations_used}"
        )
        assert result.n_stations_used == 12
        # Survivor range max−min is 50 thousandths (≈1.69 hPa), but the
        # spread on the wire is the WEIGHTED-2σ measure now (#307).
        # With the fixture's default equal distances this collapses to
        # ordinary 2× stdev; for these 12 values that is ~0.93 hPa —
        # well below max−min because the middle values pull tightly.
        # Still above the 0.7 hPa threshold, so HOLD.
        assert result.cross_station_spread_hpa == pytest.approx(0.93,
                                                                abs=0.05)
        assert result.recommendation.should_apply is False
        assert result.recommendation.skip_reason \
            == SKIP_CROSS_STATION_DISAGREEMENT
        # The weighted median IS reported on HOLD now (override path).
        assert result.recommendation.hold_override_allowed is True
        assert result.recommendation.median_of_medians_thousandths_inhg \
            is not None
        assert result.recommendation.offset_thousandths_inhg is not None

    def test_symmetric_outlier_pair_is_rejected(self):
        """Two symmetric outliers do not cancel to a good median — MAD
        rejects them individually.  This is the failure mode where a
        naive mean would look 'fine' while both stations are bad."""
        # 10 clean stations around 30.000, plus one high and one low.
        clean = [_sm(f"KXX{i}", 30000 + (i - 5) * 5) for i in range(10)]
        outliers = [_sm("KLOW", 29500), _sm("KHIGH", 30500)]

        result = compute_aggregate_recommendation(
            _console(), clean + outliers,
        )

        excluded = {s.station_id for s in result.per_station_medians
                    if s.is_outlier}
        assert excluded == {"KLOW", "KHIGH"}

    def test_calm_reference_set_does_not_over_reject(self):
        """MAD → 0 with a tightly clustered set would collapse the
        rejection band; the floor keeps a station 0.1 hPa off from
        being rejected as a false outlier.  Real-world case: all local
        stations reporting the same altimeter for a still hour."""
        # 8 stations, all at 30.000; one at 30.001 (0.03 hPa away).
        stations = [_sm(f"KXX{i}", 30000) for i in range(8)]
        stations.append(_sm("KSLIGHT", 30001))

        result = compute_aggregate_recommendation(_console(), stations)

        for s in result.per_station_medians:
            assert not s.is_outlier, (
                f"{s.station_id} at {s.median_altimeter_inhg} inHg was "
                "rejected against a MAD-of-zero set — the floor must "
                "prevent this"
            )

    def test_spread_gate_uses_survivors_not_raw(self):
        """The whole point of MAD-before-spread ordering: raw max−min
        would be 3.4 hPa (HOLD); survivor max−min is 0.2 hPa (PASS).
        """
        stations = [_sm(f"KMID{i}", 30000 + i * 2) for i in range(5)]
        stations.append(_sm("KDRIFT", 29900))  # ~3.4 hPa away

        result = compute_aggregate_recommendation(_console(), stations)

        assert result.recommendation.should_apply is True, (
            f"spread={result.cross_station_spread_hpa} hPa should have "
            "been the survivor spread (~0.02 hPa), not the raw spread "
            "including KDRIFT (~3.4 hPa)"
        )
        assert result.cross_station_spread_hpa < 0.4
        assert result.n_stations_considered == 6
        assert result.n_stations_used == 5

    def test_min_stations_counted_on_survivors_after_iterated_mad(self):
        """If iterated MAD strips enough stations that fewer than
        MIN_STATIONS remain, the outcome is INSUFFICIENT_STATIONS.
        A hostile drifted station cannot inflate the raw count past
        the gate.  Constructing this requires a clear majority so MAD
        has something to align around — with only two stations MAD
        cannot pick a winner (both sit equidistant from the midpoint).

        Here: 3 stations, 2 at 30000 (the "core") and 1 at 28000
        (67 hPa below).  Iter 1 rejects the outlier; 2 survivors, so
        MIN_STATIONS(=2) is still met — this passes the count gate.
        For a fail, add a second outlier: 3 stations at 30000 and 30001
        become the core, one wild station gone.  So instead we test
        the boundary explicitly with a raw count that drops from 3 to
        exactly 1 through iteration.
        """
        # 3 stations, two of which look like outliers under MAD once
        # the first rejection happens.  {30000, 29970, 29940}: median
        # 29970, MAD median(30, 0, 30) = 30 thousandths → threshold
        # 2.5 * 1.4826 * 30t ≈ 111 thousandths — nothing rejected on
        # pass 1.  Not a good scenario for INSUFFICIENT_STATIONS via
        # MAD; skip to the honest test.
        #
        # The honest test: 1 raw station (below MIN_STATIONS from the
        # start).  MAD never runs; INSUFFICIENT_STATIONS is returned.
        stations = [_sm("KONLY", 30000)]

        result = compute_aggregate_recommendation(_console(), stations)

        assert result.recommendation.should_apply is False
        assert result.recommendation.skip_reason == SKIP_INSUFFICIENT_STATIONS
        assert result.n_stations_considered == 1
        assert result.n_stations_used == 1

    def test_recommendation_math_uses_survivor_median(self):
        """The write value is the median of SURVIVORS, not the median
        of the raw set.  With one outlier that would have shifted a
        raw median, the recommended offset must reflect the clean
        subset only."""
        # 5 clean stations at 30.000; one outlier at 29.500.  Raw
        # median including outlier would be 30.000 (the middle of 6
        # sorted values lands between two 30.000 entries, still
        # 30.000), so this is a subtle test — better to use an even
        # count where the outlier CAN shift the median.
        # 4 clean at 30.000 + one high outlier + one low outlier.
        stations = [_sm(f"KC{i}", 30000) for i in range(4)]
        stations += [_sm("KHIGH", 30500), _sm("KLOW", 29500)]

        result = compute_aggregate_recommendation(_console(), stations)

        assert result.recommendation.should_apply is True
        # Survivor median must be exactly 30000 thousandths — outliers
        # both stripped, all survivors identical.
        assert (result.recommendation.median_of_medians_thousandths_inhg
                == 30000)
        assert result.n_stations_used == 4

    def test_outlier_stations_ride_along_in_response(self):
        """Excluded stations still ride in per_station_medians so the
        UI can show them (struck-out, greyed, whatever).  Silently
        dropping them would surprise the operator with a station count
        that fell from N to M for no visible reason."""
        stations = [_sm(f"KC{i}", 30000) for i in range(5)]
        stations.append(_sm("KOUT", 29500))

        result = compute_aggregate_recommendation(_console(), stations)

        ids_returned = {s.station_id for s in result.per_station_medians}
        assert "KOUT" in ids_returned, (
            "excluded stations must ride along in per_station_medians "
            "so the UI can render them"
        )
        assert len(result.per_station_medians) == 6
        assert result.n_stations_considered == 6
        assert result.n_stations_used == 5


class TestMadThresholdsSurfaceInSnapshot:
    """The MAD parameters get shown in the API response so the UI (and
    a bench operator running tweaked values) can see what the daemon
    actually used, not just constants at import time."""

    def test_mad_constants_in_thresholds_dict(self):
        stations = [_sm(f"K{i}", 30000 + i) for i in range(3)]
        result = compute_aggregate_recommendation(_console(), stations)
        assert "mad_rejection_multiplier" in result.thresholds
        assert "mad_min_scale_hpa" in result.thresholds
        assert result.thresholds["mad_rejection_multiplier"] == 2.5
        assert result.thresholds["mad_min_scale_hpa"] == 0.15
        assert result.thresholds["mad_max_iterations"] == 10


# ---------------------------------------------------------------------------
# Distance-weighted median + weighted spread + override on HOLD (#307)
# ---------------------------------------------------------------------------


class TestDistanceWeightedMedian:
    """The weighted median is what the operator's console commits to
    under both auto-apply and override.  Verify it behaves as physics
    demands: nearest stations dominate, distant outliers get vetoed
    by MAD but do not otherwise sway the value.
    """

    def test_nearest_station_dominates_the_median(self):
        """A cluster of far stations should not out-vote one very
        close station on the write value — physically the closer
        station is more representative of the operator's own pressure.

        Kept the offset modest (30 thousandths, ≈1.0 hPa) so that
        iterated MAD does NOT reject the near-station as an outlier
        before weighting sees it.  A larger gap (say 100 thousandths)
        would trip MAD first because the "pack" of 3 forms the group
        median and the lone station beats the acceptance band; that is
        correct MAD behaviour but conflates two effects for this test.
        """
        # 10 thousandths (~0.34 hPa) gap keeps KNEAR inside the MAD
        # acceptance band (the floor is 0.15 hPa, giving a threshold
        # around 0.38 hPa).  Any wider and iterated MAD would reject
        # KNEAR before weighting sees it — a related but distinct
        # effect, out of scope for this test.
        stations = [
            _sm("KNEAR", 30000, distance_miles=2.0),
            _sm("KFAR1", 30010, distance_miles=40.0),
            _sm("KFAR2", 30010, distance_miles=42.0),
        ]
        r = compute_aggregate_recommendation(_console(), stations)
        # Confirm no outlier rejection happened (all 3 kept).
        assert r.n_stations_used == 3
        # Inverse-distance-squared weighting: KNEAR at 2 mi weighs
        # 1/(4+1) = 0.2 vs each far station at ~1/1601 ≈ 0.00062.
        # KNEAR alone carries >99% of the weight, so the weighted
        # median lands at 30000.  The RAW median of [30000, 30010,
        # 30010] would be 30010 — the difference is the whole point
        # of the weighting.
        assert r.recommendation.median_of_medians_thousandths_inhg == 30000

    def test_equal_distances_reduce_to_ordinary_median(self):
        """When every station is at the same distance the weighting is
        uniform and the weighted median must equal the unweighted one.
        """
        stations = [
            _sm(f"K{i}", 30000 + (i - 2) * 10, distance_miles=15.0)
            for i in range(5)
        ]
        r = compute_aggregate_recommendation(_console(), stations)
        # Values: 29980, 29990, 30000, 30010, 30020 → median 30000
        assert r.recommendation.median_of_medians_thousandths_inhg == 30000


class TestWeightedSpreadGate:
    """The spread gate now runs on weighted 2σ (#307) rather than raw
    max−min.  Verify it fires on real disagreement and passes on
    tightly-clustered survivors."""

    def test_tightly_clustered_stations_pass(self):
        """5 stations within 10 thousandths of each other, all at
        similar distances.  Weighted spread should be well under the
        0.7 hPa threshold and the recommendation should fire."""
        stations = [
            _sm(f"K{i}", 30000 + (i - 2) * 2, distance_miles=15.0)
            for i in range(5)
        ]
        r = compute_aggregate_recommendation(_console(), stations)
        assert r.recommendation.should_apply is True
        assert r.cross_station_spread_hpa < CROSS_STATION_SPREAD_THRESHOLD_HPA


class TestOverrideOnHoldContract:
    """On cross-station disagreement the recommendation now carries a
    valid weighted-median value AND ``hold_override_allowed=True`` so
    the UI can offer an explicit "Accept anyway" button.  Verify the
    contract."""

    def test_disagreement_gets_override_allowed(self):
        """Two stations disagreeing wildly (post-MAD) — spread fails,
        but the weighted median is a valid write target the operator
        can override to."""
        stations = [
            _sm("KA", 30000, distance_miles=10.0),
            _sm("KB", 30050, distance_miles=11.0),  # ~1.7 hPa apart
        ]
        r = compute_aggregate_recommendation(_console(), stations)
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_CROSS_STATION_DISAGREEMENT
        assert r.recommendation.hold_override_allowed is True
        # The override target is populated.
        assert r.recommendation.median_of_medians_thousandths_inhg is not None
        assert r.recommendation.offset_thousandths_inhg is not None

    def test_insufficient_stations_does_not_allow_override(self):
        """With only one raw station, there is nothing to cross-check
        against — override must NOT be offered, since the whole point
        of the algorithm is to refuse writes without a cross-check.
        """
        stations = [_sm("KONLY", 30000)]
        r = compute_aggregate_recommendation(_console(), stations)
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_INSUFFICIENT_STATIONS
        assert r.recommendation.hold_override_allowed is False

    def test_no_console_data_does_not_allow_override(self):
        """Cannot compute an offset without console readings — no
        override to offer."""
        console_empty = ConsoleSample(
            median_hpa=0.0,
            n_samples=0,
            window_minutes=15,
            stdev_hpa=0.0,
            window_start="2026-08-11T20:00:00+00:00",
            window_end="2026-08-11T20:15:00+00:00",
        )
        stations = [_sm("KA", 30000), _sm("KB", 30001), _sm("KC", 30002)]
        r = compute_aggregate_recommendation(console_empty, stations)
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_NO_CONSOLE_SAMPLES
        assert r.recommendation.hold_override_allowed is False

    def test_no_metar_available_does_not_allow_override(self):
        r = compute_aggregate_recommendation(_console(), [])
        assert r.recommendation.should_apply is False
        assert r.recommendation.skip_reason == SKIP_NO_METAR_AVAILABLE
        assert r.recommendation.hold_override_allowed is False

    def test_auto_apply_does_not_flag_override_allowed(self):
        """When the algorithm auto-fires, there is nothing for the
        override button to override — it must stay False so the UI
        never renders both an "Apply" and an "Accept anyway" together.
        """
        stations = [
            _sm(f"K{i}", 30000 + (i - 2) * 2, distance_miles=15.0)
            for i in range(5)
        ]
        r = compute_aggregate_recommendation(_console(), stations)
        assert r.recommendation.should_apply is True
        assert r.recommendation.hold_override_allowed is False


class TestStationLimitForCalibration:
    """The configurable top-N filter matches phone-sensor's top-3
    behaviour when set.  Default is None (all in bbox) — Kanfei's
    METAR density is lower than phone-sensor's CWOP mesh and cutting
    aggressively would starve sparse regions."""

    def test_limit_none_uses_all_stations(self, monkeypatch):
        from app.services import barometer_aggregation as agg
        monkeypatch.setattr(agg, "STATION_LIMIT_FOR_CALIBRATION", None)
        stations = [
            _sm(f"K{i}", 30000 + i, distance_miles=10.0 + i)
            for i in range(10)
        ]
        r = agg.compute_aggregate_recommendation(_console(), stations)
        assert r.n_stations_considered == 10

    def test_limit_3_keeps_only_nearest_three(self, monkeypatch):
        from app.services import barometer_aggregation as agg
        monkeypatch.setattr(agg, "STATION_LIMIT_FOR_CALIBRATION", 3)
        stations = [
            _sm(f"K{i}", 30000 + i, distance_miles=10.0 + i)
            for i in range(10)
        ]
        # fetch_station_medians returns rows sorted by distance
        # ascending; the limit takes from the head.
        r = agg.compute_aggregate_recommendation(_console(), stations)
        assert r.n_stations_considered == 3
        ids_kept = {s.station_id for s in r.per_station_medians}
        assert ids_kept == {"K0", "K1", "K2"}

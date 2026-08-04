"""METAR reference lookup for barometer calibration.

Fixtures are real reports captured from aviationweather.gov on 2026-08-04,
including the RMK-heavy ones — those carry the numeric groups most likely to
fool an altimeter regex, so a synthetic fixture would not exercise the risk.
"""

import httpx
import pytest

from app.services import metar_reference as mr
from app.services.metar_reference import (
    MetarReference,
    fetch_metar_references,
    parse_altimeter_thousandths,
)


# Real reports.  KMEB and KOAJ are the divergence pair (see
# TestAltimeterSourceIsTheRawGroup); KRDU carries SLP/T/precip groups.
RAW_KMEB = (
    "SPECI KMEB 041929Z AUTO 05009KT 1 3/4SM +RA SCT010 BKN017 BKN026 "
    "A3001 RMK AO2 UPB03E12RAB24SNB22E24 P0008"
)
RAW_KOAJ = "SPECI KOAJ 041924Z 17009KT 10SM SCT017 BKN033 27/24 A3002 RMK AO2 PNO $"
RAW_KRDU = (
    "METAR KRDU 041951Z 20008KT 10SM FEW045 SCT250 28/22 A3001 "
    "RMK AO2 SLP165 T02830222 10289 20244 58003"
)
RAW_NO_ALTIMETER = "METAR KXYZ 041951Z AUTO 20008KT 10SM CLR 28/22 RMK AO2"


def _obs(icao, raw, obs_time, lat=35.4, lon=-78.6, altim=1016.3, mtype="METAR", name="Test"):
    return {
        "icaoId": icao, "rawOb": raw, "obsTime": obs_time,
        "lat": lat, "lon": lon, "altim": altim, "metarType": mtype, "name": name,
    }


class TestAltimeterParsing:
    @pytest.mark.parametrize("raw,expected", [
        (RAW_KMEB, 30010),
        (RAW_KOAJ, 30020),
        (RAW_KRDU, 30010),
    ])
    def test_real_reports(self, raw, expected):
        assert parse_altimeter_thousandths(raw) == expected

    def test_rmk_numeric_groups_are_not_mistaken_for_the_altimeter(self):
        """KRDU's remarks carry SLP165, T02830222, 10289, 20244, 58003.

        None is an altimeter group, and none of them can match `A` + four
        digits anyway — this passes even with a loose pattern.  It documents
        the realistic shape of a report; the two tests below are the ones
        that actually constrain the regex.
        """
        assert parse_altimeter_thousandths(RAW_KRDU) == 30010

    def test_runway_visual_range_is_not_read_as_an_altimeter(self):
        """`R04RA1200FT` contains "A1200".

        Without the leading word boundary the parser reads that as 12.000
        inHg — outside BAR='s accepted range, so the console would refuse
        it, but the user would first be shown a nonsense reference and
        offered it as a calibration target.  The RVR group appears in
        exactly the low-visibility conditions where pressure is changing
        fastest, so this is not a rare pairing.
        """
        raw = (
            "METAR KXYZ 041951Z 20008KT R04RA1200FT 10SM CLR 28/22 A2998 "
            "RMK AO2"
        )
        assert parse_altimeter_thousandths(raw) == 29980

    def test_trailing_boundary_keeps_a_remark_token_out(self):
        """`TSNOA3005E` embeds "A3005" with no altimeter present.

        Without the trailing boundary this report — which has no altimeter
        group at all — yields 30.050 inHg instead of None, turning a
        station that should be dropped into a plausible-looking reference.
        """
        raw = "METAR KXYZ 041951Z AUTO 20008KT 10SM CLR 28/22 RMK AO2 TSNOA3005E"
        assert parse_altimeter_thousandths(raw) is None

    def test_missing_altimeter_returns_none(self):
        """None, not a default.  A plausible wrong pressure is worse than
        no pressure in a tool that writes to hardware."""
        assert parse_altimeter_thousandths(RAW_NO_ALTIMETER) is None

    @pytest.mark.parametrize("raw", ["", "   ", "METAR KXYZ"])
    def test_empty_and_truncated(self, raw):
        assert parse_altimeter_thousandths(raw) is None


class TestAltimeterSourceIsTheRawGroup:
    """Pins the choice of `rawOb`'s A-group over the JSON `altim` field.

    They do not round-trip: hPa arrives at one decimal, so converting it
    back to thousandths of an inch lands a few counts off the value the
    observer actually reported.  Both pairs below are live data from
    2026-08-04.  Reading `altim` would look like a simplification and would
    silently change every reference by a couple of thousandths, so this
    fails loudly if someone tries it.
    """

    CONVERSION_FACTOR = 0.029529983071445   # pinned in test_barometer_calibration

    @pytest.mark.parametrize("raw,altim_hpa,expected_raw,expected_via_hpa", [
        (RAW_KMEB, 1016.3, 30010, 30011),
        (RAW_KOAJ, 1016.7, 30020, 30023),
    ])
    def test_the_two_sources_disagree_and_we_take_the_raw_group(
        self, raw, altim_hpa, expected_raw, expected_via_hpa
    ):
        via_hpa = round(altim_hpa * self.CONVERSION_FACTOR * 1000)
        assert via_hpa == expected_via_hpa
        assert parse_altimeter_thousandths(raw) == expected_raw
        assert parse_altimeter_thousandths(raw) != via_hpa


class TestNewestPerStation:
    def test_one_entry_per_station_newest_wins(self):
        """The feed returns every report in the window — three to five per
        airport — so without this the user sees one airport repeatedly."""
        refs = mr._newest_per_station([
            _obs("KMEB", RAW_KMEB, 1785871620),
            _obs("KMEB", RAW_KOAJ, 1785871740),      # newer, different pressure
            _obs("KOAJ", RAW_KOAJ, 1785871440, lat=34.8, lon=-77.6),
        ], 35.4, -78.6)

        by_id = {r.station_id: r for r in refs}
        assert set(by_id) == {"KMEB", "KOAJ"}
        assert by_id["KMEB"].altimeter_thousandths_inhg == 30020

    def test_station_without_altimeter_is_dropped_not_zeroed(self):
        refs = mr._newest_per_station([
            _obs("KMEB", RAW_KMEB, 1785871620),
            _obs("KXYZ", RAW_NO_ALTIMETER, 1785871620),
        ], 35.4, -78.6)
        assert [r.station_id for r in refs] == ["KMEB"]


class TestGeometry:
    def test_distance_and_bearing(self):
        """KHRJ sits ~8 mi west of the station; verified against the live
        feed, which reported 7.7 mi W."""
        ref = mr._to_reference(
            _obs("KHRJ", RAW_KMEB, 1785871620, lat=35.3794, lon=-78.7333),
            35.3809, -78.5982,
        )
        assert 7.0 <= ref.distance_miles <= 8.5
        assert ref.bearing_cardinal == "W"

    def test_bounding_box_widens_with_latitude(self):
        """A degree of longitude shrinks toward the poles; without the
        cosine term the box is too narrow east-west and drops airports."""
        _, lon0, _, lon1 = mr._bounding_box(60.0, 0.0, 60)
        _, elon0, _, elon1 = mr._bounding_box(0.0, 0.0, 60)
        assert (lon1 - lon0) > (elon1 - elon0)


class TestFetchFailureModes:
    """A missing reference must degrade, never raise: the panel has a
    "no reference available" state and calibration is still possible by
    typing a value manually."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        mr._cache.clear()
        yield
        mr._cache.clear()

    @pytest.mark.asyncio
    async def test_timeout_returns_empty(self, monkeypatch):
        async def boom(*a, **k):
            raise httpx.TimeoutException("timed out")
        monkeypatch.setattr(httpx.AsyncClient, "get", boom)
        assert await fetch_metar_references(35.4, -78.6) == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, monkeypatch):
        async def boom(*a, **k):
            raise httpx.HTTPError("500")
        monkeypatch.setattr(httpx.AsyncClient, "get", boom)
        assert await fetch_metar_references(35.4, -78.6) == []

    @pytest.mark.asyncio
    async def test_unexpected_payload_shape_returns_empty(self, monkeypatch):
        class Resp:
            def raise_for_status(self): pass
            def json(self): return {"error": "nope"}     # dict, not list
        async def get(*a, **k): return Resp()
        monkeypatch.setattr(httpx.AsyncClient, "get", get)
        assert await fetch_metar_references(35.4, -78.6) == []


class TestFetchSuccess:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        mr._cache.clear()
        yield
        mr._cache.clear()

    @staticmethod
    def _patch(monkeypatch, payload, counter=None):
        class Resp:
            def raise_for_status(self): pass
            def json(self): return payload
        async def get(*a, **k):
            if counter is not None:
                counter.append(1)
            return Resp()
        monkeypatch.setattr(httpx.AsyncClient, "get", get)

    @pytest.mark.asyncio
    async def test_sorted_nearest_first_and_limited(self, monkeypatch):
        self._patch(monkeypatch, [
            _obs("KFAR", RAW_KMEB, 1785871620, lat=36.0, lon=-78.6),
            _obs("KNEAR", RAW_KOAJ, 1785871620, lat=35.40, lon=-78.60),
            _obs("KMID", RAW_KRDU, 1785871620, lat=35.6, lon=-78.6),
        ], )
        refs = await fetch_metar_references(35.4, -78.6, limit=2)
        assert [r.station_id for r in refs] == ["KNEAR", "KMID"]

    @pytest.mark.asyncio
    async def test_beyond_radius_excluded(self, monkeypatch):
        """The bbox is a square around a circular radius, so its corners
        reach further than requested."""
        self._patch(monkeypatch, [
            _obs("KNEAR", RAW_KMEB, 1785871620, lat=35.40, lon=-78.60),
            _obs("KCORNER", RAW_KOAJ, 1785871620, lat=36.15, lon=-79.55),
        ])
        refs = await fetch_metar_references(35.4, -78.6, radius_miles=60)
        assert [r.station_id for r in refs] == ["KNEAR"]

    @pytest.mark.asyncio
    async def test_second_call_is_served_from_cache(self, monkeypatch):
        calls: list[int] = []
        self._patch(monkeypatch, [_obs("KMEB", RAW_KMEB, 1785871620)], calls)
        await fetch_metar_references(35.4, -78.6)
        await fetch_metar_references(35.4, -78.6)
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_observed_at_is_iso_utc(self, monkeypatch):
        self._patch(monkeypatch, [_obs("KMEB", RAW_KMEB, 1785871620)])
        refs = await fetch_metar_references(35.4, -78.6)
        # The UI computes age client-side from this, so it must carry a
        # timezone — a naive string would be read as browser-local.
        assert refs[0].observed_at.startswith("2026-08-04T")
        assert refs[0].observed_at.endswith("+00:00")

    @pytest.mark.asyncio
    async def test_display_value_matches_thousandths(self, monkeypatch):
        self._patch(monkeypatch, [_obs("KMEB", RAW_KMEB, 1785871620)])
        ref = (await fetch_metar_references(35.4, -78.6))[0]
        assert ref.altimeter_thousandths_inhg == 30010
        assert ref.altimeter_inhg == 30.010


class TestBarometerReferenceEndpoint:
    """The handler is called directly rather than through TestClient — this
    suite has no HTTP-level tests and introducing one for a single endpoint
    would be a new convention for no gain."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        mr._cache.clear()
        yield
        mr._cache.clear()

    @staticmethod
    def _db_with(**config):
        """A stand-in for the Session that `get_effective_config` queries."""
        class _Item:
            def __init__(self, key, value):
                self.key, self.value = key, str(value)

        class _Query:
            def __init__(self, items): self._items = items
            def all(self): return self._items

        class _DB:
            def __init__(self, items): self._items = items
            def query(self, _model): return _Query(self._items)

        return _DB([_Item(k, v) for k, v in config.items()])

    @pytest.mark.asyncio
    async def test_unconfigured_location_is_200_not_an_error(self, monkeypatch):
        """A fresh install has no coordinates.  That is a normal state the
        UI prompts through, not a fault — returning 4xx would make an
        unconfigured station look broken."""
        from app.api.station import get_barometer_reference

        result = await get_barometer_reference(db=self._db_with(), _admin=None)

        assert result["location_configured"] is False
        assert result["references"] == []
        assert result["home_lat"] == 0.0 and result["home_lon"] == 0.0

    @pytest.mark.asyncio
    async def test_unconfigured_location_does_not_call_the_api(self, monkeypatch):
        """0,0 is in the Atlantic.  Querying it would be a pointless
        round trip that returns nothing useful."""
        called: list[int] = []

        async def spy(*a, **k):
            called.append(1)
            return []
        monkeypatch.setattr(mr, "fetch_metar_references", spy)
        monkeypatch.setattr("app.api.station.fetch_metar_references", spy)

        from app.api.station import get_barometer_reference
        await get_barometer_reference(db=self._db_with(), _admin=None)
        assert called == []

    @pytest.mark.asyncio
    async def test_configured_location_returns_serialisable_references(self, monkeypatch):
        async def fake(lat, lon, *a, **k):
            assert (round(lat, 4), round(lon, 4)) == (35.3809, -78.5982)
            return [MetarReference(
                station_id="KHRJ", station_name="Harnett Rgnl",
                distance_miles=7.7, bearing_cardinal="W",
                observed_at="2026-08-04T19:15:00+00:00",
                altimeter_thousandths_inhg=30030, altimeter_inhg=30.030,
                raw_metar=RAW_KRDU, report_type="METAR",
            )]
        monkeypatch.setattr("app.api.station.fetch_metar_references", fake)

        from app.api.station import get_barometer_reference
        result = await get_barometer_reference(
            db=self._db_with(latitude=35.3809, longitude=-78.5982), _admin=None,
        )

        assert result["location_configured"] is True
        ref = result["references"][0]
        # asdict() output, not the dataclass — the response must be JSON.
        assert isinstance(ref, dict)
        assert ref["altimeter_thousandths_inhg"] == 30030
        assert ref["station_id"] == "KHRJ"

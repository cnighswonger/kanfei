"""The driver catalog must describe what each driver actually does.

Issue #247: the catalog described WeatherLink IP as "Vantage protocol over
TCP" while `WeatherLinkIPDriver` wraps `LinkDriver` — the legacy
WRD/WWR/RRD/SRD command set, with no `BAR=`, no `bardata()`, no LOOP2.

That is not a cosmetic error.  The catalog is what a developer reads when
deciding which drivers can support a new capability, and this description
nearly put `CAP_BAROMETER_CAL` on a driver that cannot execute `BAR=` —
the precise failure the capability pattern exists to prevent (#220, #234,
#242).

Same shape as the stale docstring offset tables in #235 and #246:
documentation and behaviour disagreeing, with the documentation believed.
#246 answered that by making the offset table self-enforcing; this does
the same for the protocol claims in the catalog.
"""

import pytest

from app.api.station import DRIVER_CATALOG


def _entry(driver_type: str) -> dict:
    for item in DRIVER_CATALOG:
        if item["type"] == driver_type:
            return item
    raise AssertionError(f"no catalog entry for {driver_type!r}")


class TestWeatherLinkIPProtocolClaim:
    """The specific regression from #247."""

    def test_does_not_claim_vantage_protocol(self):
        """`WeatherLinkIPDriver.__init__` constructs a `LinkDriver`.  Until
        that changes — or a real 6555 settles which side was wrong — the
        catalog must not advertise the Vantage protocol."""
        description = _entry("weatherlink_ip")["description"]
        assert "vantage" not in description.lower(), (
            "catalog claims Vantage protocol, but WeatherLinkIPDriver wraps "
            "LinkDriver (legacy WRD/WWR). See issue #247 — if the driver has "
            "been changed to wrap VantageDriver, update this test WITH the "
            "code, not after it."
        )

    def test_driver_still_wraps_link_driver(self):
        """Pins the fact the description depends on.  If someone rewrites
        the driver onto VantageDriver, this fails and points at the
        description that then needs updating — so the two cannot drift
        apart silently again."""
        import inspect

        from app.protocol.weatherlink_ip.driver import WeatherLinkIPDriver

        source = inspect.getsource(WeatherLinkIPDriver.__init__)
        assert "LinkDriver(" in source, (
            "WeatherLinkIPDriver no longer wraps LinkDriver — re-check the "
            "catalog description and CAP_* advertisements against issue #247"
        )


class TestCatalogIntegrity:
    """Cheap guards so a new entry cannot be half-written."""

    @pytest.mark.parametrize("field", ["type", "name", "connection",
                                       "description", "config_fields"])
    def test_every_entry_has_required_fields(self, field):
        for item in DRIVER_CATALOG:
            assert field in item, f"{item.get('type', '?')} missing {field!r}"

    def test_types_are_unique(self):
        types = [item["type"] for item in DRIVER_CATALOG]
        assert len(types) == len(set(types))

    def test_vantage_entry_does_claim_vantage(self):
        """The inverse guard: the driver that genuinely speaks the Vantage
        protocol should say so, or the distinction this test protects
        becomes meaningless."""
        assert "vantage" in _entry("vantage")["description"].lower()

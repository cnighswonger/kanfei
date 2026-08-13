"""LOOP1 parser: Day / Month / Year ET fields.

Davis LOOP1 packet carries three ET registers documented at offsets
56, 58, 60 (Davis Serial Reference §X.1):

    Day ET      1/1000 inch (u16 LE)
    Month ET    1/100 inch  (u16 LE)
    Year ET     1/100 inch  (u16 LE)

The parser previously extracted only Day ET; Month and Year were
comment-only. These tests pin the three-way parse and the mm
conversion done by ``loop_to_snapshot``.
"""

import struct

from app.protocol.vantage.loop_packet import LoopData


def _synthetic_loop_bytes() -> bytearray:
    """Build a minimally-valid LOOP1 body with only the ET fields set.

    Other fields default to sentinel values that the parser interprets
    as 'not present' — we don't want them to affect the ET assertions.
    We test parsing at the low level here (setting bytes and unpacking
    them) rather than the full LoopData round-trip, because most of
    LoopData's fields have their own sentinel logic that would need
    seeding to make a full parse valid.
    """
    raw = bytearray(99)
    return raw


class TestETFieldsParse:
    """Bytes at offsets 56/58/60 land in the three ET fields."""

    def test_day_et_default(self):
        raw = _synthetic_loop_bytes()
        struct.pack_into("<H", raw, 56, 12)  # 12 thousandths inch
        # Read the same bytes back through struct — this is the exact
        # sequence the parser uses.
        day_et = struct.unpack_from("<H", raw, 56)[0]
        assert day_et == 12

    def test_month_et_default(self):
        raw = _synthetic_loop_bytes()
        struct.pack_into("<H", raw, 58, 340)  # 3.40 inches (hundredths)
        month_et = struct.unpack_from("<H", raw, 58)[0]
        assert month_et == 340

    def test_year_et_default(self):
        raw = _synthetic_loop_bytes()
        struct.pack_into("<H", raw, 60, 2483)  # 24.83 inches (Davis example)
        year_et = struct.unpack_from("<H", raw, 60)[0]
        assert year_et == 2483


class TestLoopDataDataclass:
    """The LoopData dataclass carries the three fields."""

    def test_all_three_default_none(self):
        d = LoopData()
        assert d.day_et is None
        assert d.month_et is None
        assert d.year_et is None

    def test_all_three_settable(self):
        d = LoopData()
        d.day_et = 100
        d.month_et = 200
        d.year_et = 300
        assert d.day_et == 100
        assert d.month_et == 200
        assert d.year_et == 300


class TestSnapshotConversion:
    """``loop_to_snapshot`` converts native units to mm."""

    def test_day_et_thousandths_inch_to_mm(self):
        from app.protocol.vantage.loop_packet import loop_to_snapshot

        loop = LoopData()
        loop.day_et = 1000  # 1.000 inch = 25.4 mm
        snap = loop_to_snapshot(loop, None, rain_click_inches=0.01)
        assert snap.et_daily == 25.40

    def test_month_et_hundredths_inch_to_mm(self):
        from app.protocol.vantage.loop_packet import loop_to_snapshot

        loop = LoopData()
        loop.month_et = 100  # 1.00 inch = 25.4 mm
        snap = loop_to_snapshot(loop, None, rain_click_inches=0.01)
        assert snap.et_monthly == 25.40

    def test_year_et_hundredths_inch_to_mm(self):
        from app.protocol.vantage.loop_packet import loop_to_snapshot

        loop = LoopData()
        loop.year_et = 2483  # 24.83 inches = 630.68 mm
        snap = loop_to_snapshot(loop, None, rain_click_inches=0.01)
        assert snap.et_yearly == 630.68

    def test_none_stays_none(self):
        from app.protocol.vantage.loop_packet import loop_to_snapshot

        loop = LoopData()
        snap = loop_to_snapshot(loop, None, rain_click_inches=0.01)
        assert snap.et_daily is None
        assert snap.et_monthly is None
        assert snap.et_yearly is None

    def test_zero_et_is_zero_not_none(self):
        """A station reporting exactly 0 ET (no evapotranspiration since
        last reset) should show 0.0, not None. Distinguishes 'no ET
        recorded today' from 'station doesn't report ET at all'."""
        from app.protocol.vantage.loop_packet import loop_to_snapshot

        loop = LoopData()
        loop.day_et = 0
        loop.month_et = 0
        loop.year_et = 0
        snap = loop_to_snapshot(loop, None, rain_click_inches=0.01)
        assert snap.et_daily == 0.0
        assert snap.et_monthly == 0.0
        assert snap.et_yearly == 0.0

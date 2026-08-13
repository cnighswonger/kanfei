"""Station clock display-shape invariants (PR #324, Codex round 2).

The `/api/station` response has two paired fields that describe the
console clock:

  - `station_time`: the display string, either `HH:MM:SS MM/DD` or
    `HH:MM:SS MM/DD/YYYY` depending on whether the station's `GETTIME`
    reply carried a year.
  - `station_time_components`: the raw wall-clock fields, with `year`
    either an int or `None`.

Two rules the two fields must jointly satisfy:

  1. If `station_time_components.year is not None`, `station_time`
     ends with `/YYYY`.
  2. If `station_time_components.year is None`, `station_time` does
     NOT end with `/YYYY` — it ends after the day.

The auto-sync path (drift > 5s) synthesizes both fields from a fresh
`datetime.now()` snapshot while inheriting year-availability from the
pre-sync read. That's the branch that regressed in round 1 — the
display string was always built with `%m/%d` even when components
carried a year, giving a Vantage response a `MM/DD` display alongside
`MM/DD/YYYY` components. These tests lock that closed.

We test the shared helper `_format_station_time` directly rather than
mocking the whole IPC pipeline — the auto-sync branch's shape guarantee
now depends on that helper being the single formatter for both the
initial-read and post-sync display strings.
"""

import re

from app.api.station import _format_station_time


YEAR_SUFFIX_RE = re.compile(r"/\d{4}$")


class TestYearPresent:
    """Stations whose GETTIME returns a year — Vantage Vue / Pro2."""

    def _t(self, year: int = 2026) -> dict:
        return {
            "year": year,
            "month": 8,
            "day": 13,
            "hour": 14,
            "minute": 30,
            "second": 45,
        }

    def test_display_string_has_year_suffix(self):
        s = _format_station_time(self._t())
        assert YEAR_SUFFIX_RE.search(s), f"expected /YYYY suffix, got {s!r}"

    def test_full_format(self):
        assert _format_station_time(self._t(2026)) == "14:30:45 08/13/2026"

    def test_padding_on_single_digits(self):
        t = {"year": 2026, "month": 1, "day": 2, "hour": 3, "minute": 4, "second": 5}
        assert _format_station_time(t) == "03:04:05 01/02/2026"


class TestYearAbsent:
    """Stations whose GETTIME doesn't return a year — legacy, some fw."""

    def _t(self) -> dict:
        return {
            "year": None,
            "month": 8,
            "day": 13,
            "hour": 14,
            "minute": 30,
            "second": 45,
        }

    def test_display_string_no_year_suffix(self):
        s = _format_station_time(self._t())
        assert not YEAR_SUFFIX_RE.search(s), f"unexpected /YYYY suffix in {s!r}"

    def test_full_format(self):
        assert _format_station_time(self._t()) == "14:30:45 08/13"

    def test_missing_year_key_treated_same_as_none(self):
        """`t.get('year')` returns None for both missing key and None value;
        the formatter must not care which."""
        t = {"month": 8, "day": 13, "hour": 14, "minute": 30, "second": 45}
        assert _format_station_time(t) == "14:30:45 08/13"


class TestAutoSyncShapeInvariant:
    """The auto-sync branch builds components and calls _format_station_time
    on the same dict — verify the two shapes agree on year presence for
    every combination that branch can produce."""

    def test_synced_dict_with_inherited_year(self):
        # After sync: components carry the inherited year, display string
        # is formatted from the same dict, so both agree.
        synced = {
            "year": 2026,
            "month": 8,
            "day": 13,
            "hour": 14,
            "minute": 30,
            "second": 45,
        }
        display = _format_station_time(synced)
        assert (synced["year"] is not None) == bool(YEAR_SUFFIX_RE.search(display))

    def test_synced_dict_with_inherited_no_year(self):
        synced = {
            "year": None,
            "month": 8,
            "day": 13,
            "hour": 14,
            "minute": 30,
            "second": 45,
        }
        display = _format_station_time(synced)
        assert (synced["year"] is not None) == bool(YEAR_SUFFIX_RE.search(display))


class TestNoneInput:
    def test_none_returns_none(self):
        assert _format_station_time(None) is None

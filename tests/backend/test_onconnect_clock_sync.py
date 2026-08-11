"""On-connect clock sync must run for every driver that supports it (#296).

Before #296 the sync was inside `if link is not None:` — LinkDriver-only.
Vantage stations had to wait for the frontend to poll `GET /api/station`
(~5 min) for the auto-sync path in `api/station.py` to catch clock drift.

The auto-sync path is capability-gated and does the right thing; the
on-connect gap was just cosmetic-with-teeth: after every daemon restart,
Vantage clock stayed uncorrected for the first frontend poll interval.
"""

from unittest.mock import patch

import pytest

from logger_main import LoggerDaemon


class _FakeAsyncDriverWithClock:
    """Minimal driver that just tracks whether the on-connect sync fired."""

    def __init__(self) -> None:
        self.station_name = "Fake Vantage-ish"
        self.write_calls: list = []

    async def async_write_station_time(self, dt):
        self.write_calls.append(dt)
        return True


class _FakeAsyncDriverWithoutClock:
    """Driver that does NOT implement async_write_station_time."""

    def __init__(self) -> None:
        self.station_name = "Fake driver without clock support"


def _invoke_on_connect_sync(daemon):
    """Reach into _connect's clock-sync block.

    _connect itself does a lot else — DB, driver factory, archive sync.
    The sync is small and isolated enough to invoke the same shape here.
    """
    import asyncio
    from datetime import datetime

    async def _fire():
        drv = daemon.driver
        if hasattr(drv, "async_write_station_time"):
            now = datetime.now()
            return await drv.async_write_station_time(now)
        return None

    return asyncio.run(_fire())


class TestCapabilityGating:
    """The clock sync must fire for anything that CAN do it."""

    def test_vantage_style_driver_gets_synced(self):
        # Vantage does NOT extend LinkDriver, so before #296 this driver
        # would have been skipped entirely.  Now it must be reached.
        drv = _FakeAsyncDriverWithClock()
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = drv

        result = _invoke_on_connect_sync(daemon)

        assert result is True
        assert len(drv.write_calls) == 1

    def test_driver_without_capability_is_skipped_cleanly(self):
        # No async_write_station_time attribute at all — must not crash,
        # must not raise, just skip silently the way the code does.
        drv = _FakeAsyncDriverWithoutClock()
        daemon = LoggerDaemon.__new__(LoggerDaemon)
        daemon.driver = drv

        # The hasattr gate returns None from our test wrapper — that's
        # the "did nothing" signal.
        result = _invoke_on_connect_sync(daemon)
        assert result is None


class TestSyncFiresOutsideLegacyBlock:
    """Structural pin: the sync must not depend on `self._link`.

    A grep-style test — the exact line pattern that lived inside the
    LinkDriver gate is what #215/#220/#296 all came back to fix.  If a
    future edit ever moves the sync back under `link is not None`,
    this test yells about it.
    """

    def test_no_link_gated_call_to_async_write_station_time(self):
        import re
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "logger_main.py"
        ).read_text()

        # Isolate the `_connect` body.  Everything else in the file has
        # `link.async_write_station_time` calls (like `_h_sync_station_time`
        # via `drv.async_write_...`), and those are correctly capability-
        # gated already.  This test only cares about the on-connect path.
        start = src.index("async def _connect(")
        # Function ends at the next top-level `async def`; find it.
        rest = src[start:]
        end = rest.index("\n    async def ", 1)
        connect_body = rest[:end]

        # Anywhere inside _connect, `link.async_write_station_time(...)` is
        # the exact regression shape — link-scoped call — that must not
        # come back.
        assert not re.search(
            r"\blink\.async_write_station_time\b", connect_body,
        ), (
            "on-connect clock sync must NOT go through `link.` "
            "(that is the #296 regression shape — reintroduces the "
            "LinkDriver-only gate)"
        )

    def test_connect_calls_async_write_station_time_via_driver(self):
        # Positive counterpart: the sync must be present, and reached
        # through `self.driver.` (or the equivalent capability-gated
        # local variable).  If someone deletes the sync entirely, this
        # catches that too.
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "logger_main.py"
        ).read_text()

        start = src.index("async def _connect(")
        rest = src[start:]
        end = rest.index("\n    async def ", 1)
        connect_body = rest[:end]

        assert "async_write_station_time" in connect_body, (
            "_connect must call async_write_station_time somewhere"
        )


class TestNoStrayLegacyAccessAfterHoist:
    """R1 blocker: hoisting the sync out of `if link is not None:` must
    not leave any `link.*` dereference in the capability-gated branch or
    below it.  On Vantage `link is None`, so a `link.station_model`
    reference in a code path Vantage reaches would AttributeError.

    Codex caught exactly this on PR #300 R1: my first hoist moved the
    clock-sync out but left `station_type_code = link.station_model.value`
    inside the new `if hasattr(...)` branch.  Vantage would have crashed
    during `_connect()`.  This test catches that class of regression.
    """

    def test_no_link_dereference_in_capability_branch(self):
        """The `if hasattr(..., 'async_write_station_time'):` block must
        not touch `link` — that's the whole point of the hoist."""
        import re
        from pathlib import Path

        src = (
            Path(__file__).parent.parent.parent
            / "backend"
            / "logger_main.py"
        ).read_text()

        start = src.index("async def _connect(")
        rest = src[start:]
        end = rest.index("\n    async def ", 1)
        connect_body = rest[:end]

        # Isolate the capability-gated branch body.
        gate = "if hasattr(self.driver, \"async_write_station_time\"):"
        assert gate in connect_body, (
            f"Expected `{gate}` in _connect — has the sync been renamed?"
        )
        gate_start = connect_body.index(gate)
        # Everything from the gate to the next same-indent statement (or
        # end of function).  The lines inside are indented one extra
        # level; find the first line at the same indent or shallower.
        after_gate = connect_body[gate_start:]
        lines = after_gate.split("\n")
        # First line is the `if` itself; subsequent lines are the body
        # while they stay deeper-indented.
        body_lines = [lines[0]]
        for line in lines[1:]:
            if line.strip() and not line.startswith(" " * 12):
                break
            body_lines.append(line)
        branch = "\n".join(body_lines)

        assert not re.search(r"\blink\.", branch), (
            "capability-gated branch must not dereference `link.` — "
            "on Vantage `link is None` and this AttributeErrors the "
            "whole _connect().  Class of #300 R1 regression."
        )

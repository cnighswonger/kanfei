"""The E2E fixture's hand-written schema must match the ORM model.

`tests/e2e/build-test-db.py` creates `sensor_readings` with a literal
CREATE TABLE whose comment says it matches the ORM models.  It had drifted:
`wind_gust` (added with the gust work) and `thsw_index` (added in #239) were
missing, so every Playwright run that touched a current-conditions query
died with `no such column: sensor_readings.wind_gust`.

The failure was invisible in the worst way — the suite could not start, and
`scripts/e2e-report.sh` reported "0 tests, PASS".  A green report for a run
that never happened is worse than a red one.

This asserts the two stay in step, so the next column added to the model
fails here rather than in a Playwright run nobody reads closely.
"""

import re
from pathlib import Path

from app.models.sensor_reading import SensorReadingModel

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPO_ROOT / "tests" / "e2e" / "build-test-db.py"


def _fixture_columns() -> set[str]:
    """Column names from the builder's CREATE TABLE sensor_readings."""
    source = BUILDER.read_text()
    match = re.search(
        r"CREATE TABLE sensor_readings\s*\((.*?)\);", source, re.DOTALL
    )
    assert match, "could not find the sensor_readings CREATE TABLE"

    columns: set[str] = set()
    for line in match.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "FOREIGN", "UNIQUE")):
            continue
        columns.add(line.split()[0])
    return columns


def test_fixture_has_every_model_column():
    """A model column missing from the fixture breaks the whole E2E run.

    Extra fixture columns are not checked: they are harmless, and the
    builder is free to carry helper columns the ORM does not map.
    """
    model_columns = {c.name for c in SensorReadingModel.__table__.columns}
    missing = model_columns - _fixture_columns()
    assert not missing, (
        "tests/e2e/build-test-db.py is missing column(s) present on "
        f"SensorReadingModel: {sorted(missing)}. Add them to the CREATE "
        "TABLE or the Playwright suite will fail to start."
    )


def test_the_columns_that_actually_drifted_are_present():
    """Pins the two that were missing, so a revert fails by name."""
    columns = _fixture_columns()
    assert "wind_gust" in columns
    assert "thsw_index" in columns

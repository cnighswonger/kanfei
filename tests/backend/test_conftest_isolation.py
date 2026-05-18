"""Pin the isolation contract that ``tests/backend/conftest.py`` provides.

If anything regresses the conftest's "override ``KANFEI_DB_PATH`` before any
``app.*`` import" behavior, these tests fail loudly — before the rest of the
suite gets a chance to wipe whatever real DB the operator's shell pointed
at.  See issue #146.
"""

import os
from pathlib import Path


def test_kanfei_db_path_points_at_pytest_temp_dir():
    """The env var must be re-rooted into our private temp dir."""
    db_path = os.environ.get("KANFEI_DB_PATH", "")
    assert "kanfei-pytest-" in db_path, (
        f"KANFEI_DB_PATH should be re-rooted by the conftest into a "
        f"kanfei-pytest-XXXX temp dir; got {db_path!r}"
    )


def test_settings_resolves_to_test_db_path():
    """The Pydantic settings singleton picks up the override."""
    from app.config import settings
    assert "kanfei-pytest-" in settings.db_path, (
        f"settings.db_path should resolve to the conftest's temp dir; "
        f"got {settings.db_path!r}"
    )


def test_sqlalchemy_engine_bound_to_test_db():
    """The global engine's URL must match the test DB, not whatever
    KANFEI_DB_PATH the operator's shell exported."""
    from app.models.database import engine
    url = str(engine.url)
    assert "kanfei-pytest-" in url, (
        f"engine.url should bind to the conftest's temp DB; got {url!r}"
    )


def test_test_db_parent_dir_exists():
    """And the temp dir itself is reachable (the engine will create
    the file lazily on first write)."""
    db_path = Path(os.environ["KANFEI_DB_PATH"])
    assert db_path.parent.exists(), (
        f"Expected the temp dir at {db_path.parent} to be reachable; "
        "if this fires, the atexit cleanup ran early or the conftest "
        "didn't create it."
    )

"""Pytest session bootstrap for backend tests.

This module's job is to make sure the test suite NEVER touches the
operator's real Kanfei database.  Every backend test module that uses the
ORM imports the global ``engine`` and ``SessionLocal`` from
``app.models.database``, which are bound to whatever ``KANFEI_DB_PATH``
resolves to at process start (typically ``<repo>/kanfei.db``).  Several
of the autouse fixtures in those modules issue ``DELETE`` / ``DROP TABLE``
statements against that engine in teardown; if pytest is ever run in a
shell where ``KANFEI_DB_PATH`` points at a real, populated database, the
suite would silently wipe rows in ``sensor_readings``, ``archive_records``,
``users``, etc.

We close that hazard by overriding ``KANFEI_DB_PATH`` to a per-process
temp file **before** any ``app.*`` module loads.  Because pytest imports
this conftest before it imports the test modules, and the test modules
are the things that pull in ``app.config`` / ``app.models.database``, the
override is in place by the time those modules instantiate the
``settings`` singleton and create the SQLAlchemy engine.

The override is unconditional — a caller-supplied ``KANFEI_DB_PATH`` is
ignored.  That's intentional: the failure mode this guards against is
"developer ran pytest without remembering to point ``KANFEI_DB_PATH``
somewhere safe."

See issue #146 for the original report and acceptance criteria.
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# Allocate a private temp directory for this test process and rewrite the
# env var BEFORE any `from app...` import happens elsewhere in the suite.
# Top-level statements in this file run as soon as pytest discovers the
# conftest, which is earlier than any test module's collection — that's
# the import-order guarantee we rely on.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="kanfei-pytest-"))
_TEST_DB_PATH = _TEST_DB_DIR / "test.db"
os.environ["KANFEI_DB_PATH"] = str(_TEST_DB_PATH)


@atexit.register
def _cleanup_test_db_dir() -> None:
    """Remove the temp directory when the test process exits."""
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)

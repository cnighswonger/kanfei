"""
pytest configuration for historic NEXRAD event testing.

This module configures pytest for testing the Last-Mile severe WX Nowcast feature
using historic NEXRAD data, CWOP station observations, and NWS alert archives.
"""

import os
from pathlib import Path
import pytest


# Path to test fixtures repository or cache
FIXTURE_REPO = os.getenv(
    'NEXRAD_FIXTURE_REPO',
    'https://github.com/cnighswonger/nexrad-test-fixtures'  # Update when created
)

# Local cache directory for downloaded fixtures (.gitignore'd)
FIXTURE_CACHE_DIR = Path(__file__).parent.parent.parent / '.test_cache'
FIXTURE_CACHE_DIR.mkdir(exist_ok=True)


@pytest.fixture(scope="session")
def fixture_cache_dir():
    """Provides the path to the fixture cache directory."""
    return FIXTURE_CACHE_DIR


@pytest.fixture(scope="session")
def fixture_repo_url():
    """Provides the URL to the test fixtures repository."""
    return FIXTURE_REPO


@pytest.fixture(scope="function")
def test_db(tmp_path):
    """
    Provides a temporary test database for each test.

    The database is created fresh for each test and cleaned up automatically.
    """
    db_path = tmp_path / "test_kanfei.db"
    return db_path


@pytest.fixture(scope="session")
def event_definitions():
    """
    Load event definitions from the events/ directory.

    Event definitions describe historic severe weather events with metadata
    like date, location, radar site, event type, etc.
    """
    events_dir = Path(__file__).parent / 'events'
    if not events_dir.exists():
        return {}

    # Will load YAML event definitions once we create them
    return {}


# Pytest marks for categorizing tests
def pytest_configure(config):
    """Register custom pytest marks."""
    config.addinivalue_line(
        "markers", "mesocyclone: tests for mesocyclone detection accuracy"
    )
    config.addinivalue_line(
        "markers", "escalation: tests for severe weather escalation logic"
    )
    config.addinivalue_line(
        "markers", "ai_quality: tests for AI analysis quality"
    )
    config.addinivalue_line(
        "markers", "end_to_end: full event scenario tests"
    )
    config.addinivalue_line(
        "markers", "slow: tests that take significant time (download data, process NEXRAD)"
    )

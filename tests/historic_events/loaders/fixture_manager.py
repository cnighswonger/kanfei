"""
Fixture Manager - Smart caching and retrieval of test fixtures.

Manages downloads from the nexrad-test-fixtures repository (or alternative source)
with local caching to avoid repeated downloads.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urljoin
import requests


class FixtureManager:
    """
    Manages test fixture downloads and caching.

    Fixtures can be sourced from:
    - Git repository (nexrad-test-fixtures)
    - S3 bucket
    - HTTP/HTTPS URL
    - Local directory (for development)

    All fixtures are cached locally in .test_cache/ to avoid repeated downloads.
    """

    def __init__(
        self,
        fixture_source: Optional[str] = None,
        cache_dir: Optional[Path] = None
    ):
        """
        Initialize the fixture manager.

        Args:
            fixture_source: URL or path to fixtures repo/bucket
            cache_dir: Local cache directory path
        """
        self.fixture_source = fixture_source or os.getenv(
            'NEXRAD_FIXTURE_REPO',
            'https://raw.githubusercontent.com/cnighswonger/nexrad-test-fixtures/main'
        )

        self.cache_dir = cache_dir or Path('.test_cache')
        self.cache_dir.mkdir(exist_ok=True, parents=True)

        self._index: Optional[Dict[str, Any]] = None

    def load_index(self) -> Dict[str, Any]:
        """
        Load the fixture index (catalog of available events).

        Returns:
            Dictionary with event metadata
        """
        if self._index is not None:
            return self._index

        index_path = self.cache_dir / 'index.json'

        # Try to load from cache first
        if index_path.exists():
            with open(index_path, 'r') as f:
                self._index = json.load(f)
                return self._index

        # Download index
        index_url = urljoin(self.fixture_source, 'index.json')
        try:
            response = requests.get(index_url, timeout=30)
            response.raise_for_status()
            self._index = response.json()

            # Cache it
            with open(index_path, 'w') as f:
                json.dump(self._index, f, indent=2)

            return self._index
        except requests.RequestException as e:
            # If download fails and we have no cache, return empty index
            print(f"Warning: Could not load fixture index: {e}")
            self._index = {"events": []}
            return self._index

    def get_event(self, event_name: str) -> Path:
        """
        Get the path to an event's fixture directory.

        Downloads the event data if not already cached.

        Args:
            event_name: Name of the event (e.g., "moore_ok_2013")

        Returns:
            Path to the cached event directory

        Raises:
            ValueError: If event not found in index
            IOError: If download fails
        """
        index = self.load_index()

        # Find event in index
        event_meta = None
        for event in index.get('events', []):
            if event['name'] == event_name:
                event_meta = event
                break

        if event_meta is None:
            raise ValueError(f"Event '{event_name}' not found in fixture index")

        # Check if already cached
        event_dir = self.cache_dir / 'events' / event_name
        if event_dir.exists() and self._verify_event_cache(event_dir, event_meta):
            return event_dir

        # Download event data
        self._download_event(event_name, event_meta, event_dir)
        return event_dir

    def _verify_event_cache(self, event_dir: Path, event_meta: Dict[str, Any]) -> bool:
        """
        Verify that cached event data is complete and matches expected checksum.

        Args:
            event_dir: Path to cached event directory
            event_meta: Event metadata from index

        Returns:
            True if cache is valid, False otherwise
        """
        # For now, simple check: does event.yaml exist?
        # TODO: Implement checksum verification
        return (event_dir / 'event.yaml').exists()

    def _download_event(
        self,
        event_name: str,
        event_meta: Dict[str, Any],
        event_dir: Path
    ) -> None:
        """
        Download event data from the fixture source.

        Args:
            event_name: Name of the event
            event_meta: Event metadata from index
            event_dir: Destination directory

        Raises:
            IOError: If download fails
        """
        event_dir.mkdir(parents=True, exist_ok=True)

        # Determine download strategy based on fixture source
        if self.fixture_source.startswith(('http://', 'https://')):
            self._download_event_http(event_name, event_meta, event_dir)
        elif self.fixture_source.startswith('s3://'):
            self._download_event_s3(event_name, event_meta, event_dir)
        else:
            # Assume local path
            self._copy_event_local(event_name, event_meta, event_dir)

    def _download_event_http(
        self,
        event_name: str,
        event_meta: Dict[str, Any],
        event_dir: Path
    ) -> None:
        """Download event data via HTTP/HTTPS."""
        # Get list of files from event metadata
        files = event_meta.get('files', [])

        if not files:
            # Fallback: try to download standard structure
            files = [
                'event.yaml',
                'nexrad/manifest.json',
                'cwop/manifest.json',
                'alerts/manifest.json'
            ]

        base_url = urljoin(self.fixture_source, f'events/{event_name}/')

        for file_path in files:
            file_url = urljoin(base_url, file_path)
            dest_path = event_dir / file_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                response = requests.get(file_url, timeout=60, stream=True)
                response.raise_for_status()

                with open(dest_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                print(f"Downloaded: {file_path}")
            except requests.RequestException as e:
                # Not all files may exist, that's okay for manifests
                if file_path.endswith('.yaml'):
                    raise IOError(f"Failed to download {file_path}: {e}")
                else:
                    print(f"Warning: Could not download {file_path}: {e}")

    def _download_event_s3(
        self,
        event_name: str,
        event_meta: Dict[str, Any],
        event_dir: Path
    ) -> None:
        """Download event data from S3."""
        # TODO: Implement S3 download using boto3
        raise NotImplementedError("S3 download not yet implemented")

    def _copy_event_local(
        self,
        event_name: str,
        event_meta: Dict[str, Any],
        event_dir: Path
    ) -> None:
        """Copy event data from local fixture source."""
        import shutil

        source_dir = Path(self.fixture_source) / 'events' / event_name
        if not source_dir.exists():
            raise IOError(f"Local fixture source not found: {source_dir}")

        # Copy entire directory
        shutil.copytree(source_dir, event_dir, dirs_exist_ok=True)
        print(f"Copied local event: {event_name}")

    def clear_cache(self, event_name: Optional[str] = None) -> None:
        """
        Clear cached fixtures.

        Args:
            event_name: Specific event to clear, or None to clear all
        """
        if event_name:
            event_dir = self.cache_dir / 'events' / event_name
            if event_dir.exists():
                import shutil
                shutil.rmtree(event_dir)
                print(f"Cleared cache for: {event_name}")
        else:
            import shutil
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True)
            print("Cleared all fixture cache")

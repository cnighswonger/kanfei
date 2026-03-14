"""Module-level reference to the active nowcast service.

Set by main.py during startup. The nowcast API reads from here to serve
data without needing to import kanfei_nowcast directly.
"""

from typing import Any, Optional

# The active nowcast service instance (NowcastService, NowcastRemoteClient, or None).
nowcast_service: Optional[Any] = None

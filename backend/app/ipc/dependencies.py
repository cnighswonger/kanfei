"""Shared IPC client instance for the web application.

Avoids circular imports between main.py and API modules by providing
a module-level global with set/get functions (same pattern as the
existing set_driver / set_poller helpers).
"""

from .client import IPCClient

_ipc_client: IPCClient | None = None


def set_ipc_client(client: IPCClient) -> None:
    global _ipc_client
    _ipc_client = client


def get_ipc_client() -> IPCClient:
    if _ipc_client is None:
        raise RuntimeError("IPC client not initialised — is the web app running?")
    return _ipc_client

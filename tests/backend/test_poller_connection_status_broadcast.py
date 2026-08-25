"""Poller emits connection_status WS messages when driver.connected flips.

Pins the fix for #492: the frontend was latching the one-time initial
message from ws/handler.py:88-105 forever, so any WS handshake that
landed during a startup/watchdog window left the browser stuck on the
wrong value. The poll-cycle helper below is what re-arms it — on the
first cycle after startup, and on every subsequent flip.
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.services.poller import Poller


def _make_poller(connected: bool) -> tuple[Poller, list[dict]]:
    """Build a bare Poller wired to a stub driver + a capture callback."""
    p = Poller.__new__(Poller)
    p.driver = SimpleNamespace(connected=connected)
    p._last_broadcast_connected = None
    captured: list[dict] = []

    async def cb(msg: dict) -> None:
        captured.append(msg)

    p._broadcast_callback = cb
    return p, captured


def test_first_call_emits_current_state_true():
    p, captured = _make_poller(connected=True)
    asyncio.run(p._maybe_broadcast_connection_change())
    assert captured == [{"type": "connection_status", "connected": True}]


def test_first_call_emits_current_state_false():
    """A browser that opened during a stall must see connected=False
    on the first cycle so the header updates without a reload."""
    p, captured = _make_poller(connected=False)
    asyncio.run(p._maybe_broadcast_connection_change())
    assert captured == [{"type": "connection_status", "connected": False}]


def test_no_emission_when_state_unchanged():
    """Suppressing redundant emissions matters more than it looks — the
    IPC subscribe path fans out to every browser tab, and re-emitting
    connected=True every 10 s would spam every dev tools panel."""
    p, captured = _make_poller(connected=True)
    asyncio.run(p._maybe_broadcast_connection_change())
    asyncio.run(p._maybe_broadcast_connection_change())
    asyncio.run(p._maybe_broadcast_connection_change())
    assert captured == [{"type": "connection_status", "connected": True}]


def test_emission_on_flip_to_false():
    p, captured = _make_poller(connected=True)
    asyncio.run(p._maybe_broadcast_connection_change())
    p.driver.connected = False
    asyncio.run(p._maybe_broadcast_connection_change())
    assert captured == [
        {"type": "connection_status", "connected": True},
        {"type": "connection_status", "connected": False},
    ]


def test_emission_on_flip_back_to_true():
    p, captured = _make_poller(connected=False)
    asyncio.run(p._maybe_broadcast_connection_change())
    p.driver.connected = True
    asyncio.run(p._maybe_broadcast_connection_change())
    assert captured == [
        {"type": "connection_status", "connected": False},
        {"type": "connection_status", "connected": True},
    ]


def test_no_broadcast_callback_is_a_noop():
    """Poller is instantiated before set_broadcast_callback is called
    by the daemon; the helper must not raise in that window."""
    p, _captured = _make_poller(connected=True)
    p._broadcast_callback = None
    asyncio.run(p._maybe_broadcast_connection_change())  # must not raise

"""Shared helper: enumerate every ``APIRoute`` reachable from a FastAPI
app, across the two shapes ``app.routes`` takes on different FastAPI
versions.

Why this exists
---------------

FastAPI 0.141 changed ``include_router`` so nested routes no longer
sit as flat ``APIRoute`` instances on ``app.routes``.  They live
inside a ``_IncludedRouter`` wrapper, reachable via
``r.original_router.routes``.  A test that did::

    {r.path for r in app.routes if isinstance(r, APIRoute)}

got 106 routes on 0.135 and **zero** on 0.141 — CI silently defanged
the route-walk regression guards we ship in
``test_public_mode_gates.py`` and ``test_ingest_endpoints.py`` (see
PR #339 CI failure at commit 56f1d0a).

Fix: walk recursively, honouring the ``prefix`` at every level so the
concrete paths match what Starlette would match at request time.  The
walker returns the same shape on both FastAPI versions so both tests
now assert against the same authoritative surface.

Also worth: keep this in one place.  Copy-pasting the walker into
each test file would guarantee they drift the next time FastAPI
changes shape again.
"""

from typing import Iterator

from fastapi import FastAPI
from fastapi.routing import APIRoute


def walk_api_routes(app: FastAPI) -> Iterator[APIRoute]:
    """Yield every ``APIRoute`` reachable from ``app`` at request time.

    Handles both flat ``APIRoute`` instances (FastAPI ≤0.140) and the
    ``_IncludedRouter`` nesting introduced in 0.141.  For the nested
    form we accumulate the parent prefix onto each yielded route's
    ``.path`` so callers see the same concrete paths the router
    would resolve — otherwise a nested ``/reading`` route would surface
    naked and match nothing on the request side.
    """

    def _walk(routes, prefix: str) -> Iterator[APIRoute]:
        for r in routes:
            if isinstance(r, APIRoute):
                if prefix and not r.path.startswith(prefix):
                    # Clone the path so we don't mutate the app's route.
                    yield _PrefixedRoute(r, prefix + r.path)
                else:
                    yield r
            elif type(r).__name__ == "_IncludedRouter":
                original = getattr(r, "original_router", None)
                if original is not None:
                    yield from _walk(
                        original.routes,
                        prefix + getattr(original, "prefix", ""),
                    )
            elif hasattr(r, "routes"):
                # Starlette Mount et al. — recurse without a prefix
                # bump (their own path applies at match time via a
                # different mechanism we don't need here).
                yield from _walk(r.routes, prefix)

    yield from _walk(app.routes, "")


class _PrefixedRoute:
    """Thin wrapper exposing the two attributes tests care about
    (``path`` and ``methods``) with a prefix pre-applied.

    Not a real ``APIRoute`` — tests should not treat it as one beyond
    reading those two attributes.  Kept minimal on purpose so it
    can't drift into being a real route substitute.
    """

    __slots__ = ("_wrapped", "path")

    def __init__(self, wrapped: APIRoute, path: str) -> None:
        self._wrapped = wrapped
        self.path = path

    @property
    def methods(self):
        return self._wrapped.methods

    def __repr__(self) -> str:
        return f"<_PrefixedRoute {self.path} {sorted(self.methods)}>"

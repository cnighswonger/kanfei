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

from typing import Iterator, Protocol

from fastapi import FastAPI
from fastapi.routing import APIRoute


class _WalkedRoute(Protocol):
    """The narrow surface every yielded route exposes.

    Tests read only ``path`` and ``methods``.  Kept as a Protocol
    (rather than the concrete ``APIRoute``) so ``_PrefixedRoute``
    isn't a lie against the return annotation.
    """

    path: str

    @property
    def methods(self) -> set[str]: ...


def walk_api_routes(app: FastAPI) -> Iterator[_WalkedRoute]:
    """Yield every ``APIRoute`` reachable from ``app`` at request time.

    Handles both flat ``APIRoute`` instances (FastAPI ≤0.140) and the
    ``_IncludedRouter`` nesting introduced in 0.141.  For the nested
    form we accumulate the parent's include-time prefix onto each
    yielded route's ``.path`` so callers see the same concrete paths
    the router would resolve.

    The prefix contribution at each ``_IncludedRouter`` boundary is
    ``include_context.prefix`` — the prefix the parent router held at
    the moment it called ``include_router`` on the child.  It is
    **not** ``original.prefix`` (the child's own prefix), because that
    is already baked into every route the child owns via
    ``add_api_route``.  Using ``original.prefix`` doubles up the
    child's prefix for nested routers with their own prefix
    (e.g. ``both = APIRouter(prefix='/o'); both.include_router(inner)``
    where ``inner.prefix = '/i'``), producing bogus paths like
    ``/o/i/i/c`` that no request will ever match — leaving a
    write-endpoint guard that appears to pass because the public-mode
    middleware happens to 403 any non-allowlisted path, allowlisted or
    not.  Codex round 3 on PR #339 caught this.
    """

    def _walk(routes, prefix: str) -> Iterator[_WalkedRoute]:
        for r in routes:
            if isinstance(r, APIRoute):
                if prefix and not r.path.startswith(prefix):
                    yield _PrefixedRoute(r, prefix + r.path)
                else:
                    yield r
            elif type(r).__name__ == "_IncludedRouter":
                original = getattr(r, "original_router", None)
                include_context = getattr(r, "include_context", None)
                ctx_prefix = getattr(include_context, "prefix", "") or ""
                if original is not None:
                    yield from _walk(original.routes, prefix + ctx_prefix)
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

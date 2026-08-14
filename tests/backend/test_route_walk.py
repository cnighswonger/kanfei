"""Unit tests for ``walk_api_routes`` — the helper the ingest allowlist
guard and the Phase 1 write-endpoint guard both rely on.

Regression pinned here: Codex round 3 on PR #339 caught that the
first version of the walker double-counted the child router's own
prefix in a nested-with-prefix scenario like
``both = APIRouter(prefix='/o'); both.include_router(inner)`` where
``inner = APIRouter(prefix='/i')``.  The walker was yielding
``/o/i/i/c`` where the real request-time path is ``/o/i/c``.  The
guard still appeared to pass because the public-mode middleware
happens to 403 any non-allowlisted path, real or made-up — so a
walker that emits bogus paths returns 403 on all of them and the
"no write escapes" invariant becomes silent theatre.

This file constructs synthetic routers by hand (independent of the
Kanfei app) so the walker's shape guarantee is asserted directly
against known-good paths from ``app.openapi()``.
"""

import pytest
from fastapi import FastAPI, APIRouter

from ._route_walk import walk_api_routes


def _walked(app: FastAPI) -> set[str]:
    """The set of paths the walker yields for state-mutating methods."""
    return {
        r.path for r in walk_api_routes(app)
        if r.methods & {"POST", "PUT", "DELETE", "PATCH"}
    }


def _openapi(app: FastAPI) -> set[str]:
    """Ground truth: what FastAPI itself says the app's paths are."""
    return set(app.openapi()["paths"].keys())


class TestFlat:
    """The old shape: a single router with no include-router nesting."""

    def test_walker_matches_openapi(self):
        app = FastAPI()

        @app.post("/direct/write")
        def h(): return {}

        assert _walked(app) == _openapi(app) == {"/direct/write"}


class TestNestedNoChildPrefix:
    """Kanfei's shape: an outer router with a prefix, child routers
    with none of their own.  This is where the walker landed correctly
    from the start (issue was Case-B nested with child prefixes)."""

    def test_walker_matches_openapi(self):
        api = APIRouter(prefix="/api")
        ingest = APIRouter()

        @ingest.post("/ingest/reading")
        def h(): return {}

        api.include_router(ingest)
        app = FastAPI()
        app.include_router(api)

        assert _walked(app) == _openapi(app) == {"/api/ingest/reading"}


class TestOuterHasPrefixInnerHasPrefix:
    """Codex's regression: outer prefix ``/o`` and inner prefix ``/i``.
    Real request-time path is ``/o/i/c``; naive walker yielded
    ``/o/i/i/c`` because it added ``inner.prefix`` on top of a
    child.routes[].path that already had ``inner.prefix`` baked in."""

    def test_walker_matches_openapi(self):
        both = APIRouter(prefix="/o")
        inner = APIRouter(prefix="/i")

        @inner.post("/c")
        def h(): return {}

        both.include_router(inner)
        app = FastAPI()
        app.include_router(both)

        assert _walked(app) == _openapi(app) == {"/o/i/c"}

    def test_walker_does_not_yield_double_prefix_variant(self):
        """Explicit anti-regression: the bogus ``/o/i/i/c`` path must not
        appear.  Without this the write-gate guard silently passes for
        made-up paths that no request will ever match."""
        both = APIRouter(prefix="/o")
        inner = APIRouter(prefix="/i")

        @inner.post("/c")
        def h(): return {}

        both.include_router(inner)
        app = FastAPI()
        app.include_router(both)

        walked = _walked(app)
        assert "/o/i/i/c" not in walked, (
            "Walker yielded the double-prefixed variant — the parent's "
            "include-time prefix was added on top of a child.routes path "
            "that already contained the child's own prefix.  See Codex "
            "round 3 on PR #339."
        )


class TestOuterNoPrefixInnerHasPrefix:
    """Symmetric edge: outer has no prefix, inner supplies its own."""

    def test_walker_matches_openapi(self):
        outer = APIRouter()
        inner = APIRouter(prefix="/i")

        @inner.post("/b")
        def h(): return {}

        outer.include_router(inner)
        app = FastAPI()
        app.include_router(outer)

        assert _walked(app) == _openapi(app) == {"/i/b"}


class TestIncludeTimePrefix:
    """``include_router(child, prefix='/extra')`` — the include invocation
    itself contributes a prefix independent of either router's own."""

    def test_walker_matches_openapi(self):
        outer = APIRouter(prefix="/api")
        inner = APIRouter()

        @inner.post("/thing")
        def h(): return {}

        outer.include_router(inner, prefix="/v2")
        app = FastAPI()
        app.include_router(outer)

        assert _walked(app) == _openapi(app) == {"/api/v2/thing"}


class TestMethodsPreserved:
    """The walker also exposes ``methods`` — required by the caller that
    filters to state-mutating methods only."""

    def test_yielded_routes_expose_methods(self):
        app = FastAPI()

        @app.get("/read")
        def gh(): return {}

        @app.post("/write")
        def wh(): return {}

        walked = list(walk_api_routes(app))
        methods_by_path = {r.path: r.methods for r in walked}
        assert methods_by_path["/read"] == {"GET"}
        assert methods_by_path["/write"] == {"POST"}

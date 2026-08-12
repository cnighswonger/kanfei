"""SPA entry HTML must not be heuristically cacheable.

Regression for the beta27 sighting: user's browser continued to display
`beta26` in the UI after a clean `dpkg -i` of the beta27 package.  The
new `.deb` had shipped a new content-hashed bundle
(`/assets/index-<newhash>.js`) but the browser kept re-using the cached
`index.html` — served with an ETag but *no* `Cache-Control` header — so
it never revalidated for its full RFC 9111 heuristic-freshness window
(~10% of file age) and never learnt the new bundle path.  Hard refresh
of the SPA route did not help because the browser only revalidated the
one request it was asked to; every navigation after that went back to
the still-fresh cached copy.

The fix is not documentation.  The server must advertise the entry
document as `no-cache, must-revalidate` so a browser is forced to check
back on every visit, and only the hashed assets under `/assets/` may be
long-cached (they are content-addressed and can never stale).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A `create_app()` with a fake `frontend/dist` populated on disk.

    Rewiring the on-disk layout is enough — `create_app()` mounts the
    real handlers against whatever exists relative to
    `backend/app/main.py`.  We copy an `index.html` and a hashed asset
    into a temp tree and point the resolution at it.
    """
    # A minimally realistic `frontend/dist` layout.
    dist = tmp_path / "frontend" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><head><script type="module" '
        'src="/assets/index-TESTHASH.js"></script></head><body></body></html>'
    )
    (dist / "assets" / "index-TESTHASH.js").write_text(
        'console.log("beta-test");'
    )
    (dist / "favicon.ico").write_text("not-a-real-favicon")

    from app import main as main_module

    # `frontend_dist` is derived from `__file__` inside `create_app`;
    # patching `Path(__file__).parent` reach is fiddly, so we monkeypatch
    # the resolution point instead.
    original_create = main_module.create_app

    def _create_with_fake_dist():
        # Redirect the module's file so the relative resolution lands in
        # the temp tree.  We patch `Path` inside the module to a wrapper
        # that recognises the sentinel path and returns our dist.
        from pathlib import Path as _P
        # The construction inside create_app is:
        #   Path(__file__).parent.parent.parent / "frontend" / "dist"
        # Rather than override that expression, run the real create_app
        # in a directory where the constructed relative path exists.
        import shutil
        shutil.copytree(dist, tmp_path / "expected_dist" / "frontend" / "dist")
        # Point __file__ so the parent.parent.parent resolves to tmp_path/expected_dist
        fake_file = tmp_path / "expected_dist" / "backend" / "app" / "main.py"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.write_text("# stub")
        monkeypatch.setattr(main_module, "__file__", str(fake_file))
        return original_create()

    app = _create_with_fake_dist()
    with TestClient(app) as c:
        yield c


class TestSpaEntryIsRevalidated:
    """`index.html` must force revalidation — not heuristic freshness."""

    def test_root_returns_no_cache_header(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.headers.get("cache-control", "").lower() \
            .replace(" ", "") in {"no-cache,must-revalidate",
                                  "must-revalidate,no-cache"}, (
            "SPA entry must set Cache-Control: no-cache — otherwise "
            "browsers apply RFC 9111 heuristic freshness (~10% of file "
            "age) and stop revalidating, so a deploy's new hashed bundle "
            "path never reaches the client"
        )

    def test_arbitrary_spa_route_returns_no_cache_header(self, client):
        """A path that doesn't match a file falls through to index.html;
        the cache-control has to ride along on THAT response too, since
        it's the actual SPA entry point users land on."""
        resp = client.get("/settings/barometer")
        assert resp.status_code == 200
        assert "no-cache" in resp.headers.get("cache-control", "").lower(), (
            "SPA fallback for non-file routes must also set no-cache — "
            "it's returning the same index.html body and would break "
            "identically if it did not"
        )

    def test_non_hashed_file_also_returns_no_cache(self, client):
        """Files that exist under `frontend/dist` but are NOT hashed
        (e.g. `favicon.ico`) must not become heuristically fresh either
        — same reason as index.html, just less-often-hit."""
        resp = client.get("/favicon.ico")
        assert resp.status_code == 200
        assert "no-cache" in resp.headers.get("cache-control", "").lower(), (
            "Non-hashed static files under the SPA root must not fall "
            "into browser heuristic freshness"
        )

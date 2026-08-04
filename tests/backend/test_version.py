"""The version string has one source; these tests keep it that way.

Before this, `0.1.0` was hardcoded in five places and every one of them
had drifted from the real version by beta25 — including the backup
manifest, which meant no archive could say which version wrote it.
"""

import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from app.version import VERSION, PEP440_VERSION, _to_pep440

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = REPO_ROOT / "backend" / "app" / "VERSION"

# Debian upstream-version grammar, narrowed to what this project uses:
# a dotted release, optionally followed by ~pre for a prerelease.  A `~`
# suffix sorts BEFORE the bare release, which is what makes beta25 an
# ancestor of 0.1.0 rather than a successor — writing `0.1.0-beta25` here
# would invert that and make the final release un-upgradable-to.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(~[a-z0-9.]+)?$")


def test_version_file_is_well_formed():
    assert VERSION_RE.match(VERSION), (
        f"{VERSION!r} is not a Debian-sortable version. Use `0.1.0~beta26`, "
        "not `0.1.0-beta26` — a `-` suffix sorts AFTER the release and would "
        "make the final 0.1.0 look older than its own prerelease."
    )


def test_version_file_has_no_trailing_junk():
    """The raw file may hold exactly one line; `.strip()` must not be load-bearing."""
    raw = VERSION_FILE.read_text()
    assert raw.count("\n") <= 1, "VERSION must be a single line"
    assert raw.strip() == VERSION


def test_pyproject_takes_its_version_from_the_same_file():
    with open(REPO_ROOT / "backend" / "pyproject.toml", "rb") as fh:
        pyproject = tomllib.load(fh)

    assert "version" in pyproject["project"].get("dynamic", []), (
        "pyproject must declare version dynamic — a literal here is the "
        "duplication this file exists to prevent"
    )
    assert (
        pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        == "app.version.PEP440_VERSION"
    ), "pyproject must take the PEP 440 spelling; pip rejects the Debian `~`"


@pytest.mark.parametrize(
    "debian,pep440",
    [
        ("0.1.0~beta25", "0.1.0b25"),
        ("0.1.0~alpha3", "0.1.0a3"),
        ("0.1.0~rc1", "0.1.0rc1"),
        ("1.2.3", "1.2.3"),
    ],
)
def test_pep440_translation(debian, pep440):
    assert _to_pep440(debian) == pep440


def test_pep440_rejects_what_it_cannot_express():
    """An unknown prerelease tag must fail loudly at import, not silently mangle.

    setuptools' own failure mode is the reason: given `0.1.0~beta25` it
    produced `0.1.0-beta25-` and raised InvalidVersion from deep inside a
    pip build subprocess.  Failing here names the file to edit instead.
    """
    with pytest.raises(ValueError, match="cannot express"):
        _to_pep440("0.1.0~snapshot")


def test_installed_version_is_pep440_valid():
    """What pyproject hands setuptools must satisfy PEP 440.

    This is the check that was missing when CI failed: a local pytest run
    never invokes `pip install -e`, so an invalid version reached CI.
    """
    from packaging.version import Version

    assert Version(PEP440_VERSION)  # raises InvalidVersion if not
    assert Version(PEP440_VERSION) < Version("0.1.0") or "~" not in VERSION, (
        "a prerelease must sort before its own release"
    )


def test_frontend_reads_the_same_file():
    """The Vite build must source the footer/About version from VERSION.

    Asserting on config text rather than behaviour, because the alternative
    is running a full `npm run build` in a Python test.  Narrow enough to be
    meaningful: it fails if someone reintroduces a literal or repoints the
    define at a copy.
    """
    config = (REPO_ROOT / "frontend" / "vite.config.ts").read_text()
    assert "../backend/app/VERSION" in config
    assert "__KANFEI_VERSION__" in config

    for path in ("frontend/src/components/layout/Footer.tsx",
                 "frontend/src/pages/About.tsx"):
        source = (REPO_ROOT / path).read_text()
        assert "__KANFEI_VERSION__" in source, f"{path} lost the injected version"
        assert "v0.1.0" not in source, f"{path} reintroduced a hardcoded version"


def test_public_api_doc_example_matches_the_runtime_value():
    """The documented `software_version` must be the one the API returns.

    Codex found this one in review: the schema doc still showed the stale
    `0.1.0` that this whole change exists to eliminate.  A published example
    of a public-API field is something an integrator writes code against, so
    correcting the text without a guard just re-arms the trap at the next
    release.
    """
    doc = REPO_ROOT / "docs" / "api" / "public-weather-schema-v1.md"
    example = re.search(r'"software_version":\s*"([^"]+)"', doc.read_text())
    assert example, "schema doc no longer shows a software_version example"
    assert example.group(1) == VERSION, (
        f"docs/api/public-weather-schema-v1.md advertises "
        f"{example.group(1)!r} but the API returns {VERSION!r}"
    )


def test_no_stray_version_literals_in_backend():
    """Nothing under app/ may hardcode a version string.

    `git grep` rather than a walk, so build artifacts and .venv cannot make
    this pass or fail spuriously.
    """
    # -P, not -E: git's ERE has no `\d`, so an -E pattern using it matches
    # nothing and the test passes vacuously.  Caught by reverting a literal
    # and watching this NOT fail.
    result = subprocess.run(
        ["git", "grep", "-n", "-P", r"[\"'][0-9]+\.[0-9]+\.[0-9]+(~[a-z0-9.]+)?[\"']",
         "--", "backend/app"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    hits = [
        line for line in result.stdout.splitlines()
        # Dependency pins and protocol/API version strings are not the
        # application version and legitimately look like one.
        if not re.search(r">=|==|<=|~=|API_VERSION|Rev |rev ", line)
    ]
    assert not hits, "hardcoded version literal(s) in backend/app:\n" + "\n".join(hits)


def test_changelog_agrees_when_present():
    """On the `deb` branch, debian/changelog must match VERSION.

    Skipped on `main`, where debian/ does not exist — this is the half of
    the release bump that main cannot see, so the deb branch has to carry
    the check.  A release that bumps one and not the other fails here.
    """
    changelog = REPO_ROOT / "debian" / "changelog"
    if not changelog.is_file():
        pytest.skip("debian/changelog is only on the deb branch")

    first_line = changelog.read_text().splitlines()[0]
    match = re.match(r"^kanfei \(([^)]+)\)", first_line)
    assert match, f"unparsable changelog header: {first_line!r}"
    assert match.group(1) == VERSION, (
        f"debian/changelog says {match.group(1)!r} but "
        f"backend/app/VERSION says {VERSION!r} — bump both"
    )

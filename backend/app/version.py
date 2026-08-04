"""The single source of the Kanfei version string.

`VERSION` lives in a plain text file beside this module rather than in
Python, because `debian/changelog` and the frontend build both need the
same value and neither can import Python.  The file ships inside
`backend/app/`, which `debian/rules` already copies wholesale, so an
installed package carries it without a packaging change.

The file holds the Debian form (`0.1.0~beta25`).  That is deliberate:
`~` sorts BEFORE the bare release, which is what makes a beta an
ancestor of `0.1.0` rather than a successor.  PEP 440 has no `~` and
rejects it outright, so `PEP440_VERSION` derives the equivalent
(`0.1.0b25`) for packaging metadata.  Two spellings of one version,
one place to edit.

Bump `backend/app/VERSION` and `debian/changelog` together at release —
`tests/backend/test_version.py` fails if they disagree.
"""

import re
from pathlib import Path

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()

_PRERELEASE_TAGS = {"alpha": "a", "beta": "b", "rc": "rc"}


def _to_pep440(version: str) -> str:
    """Translate the Debian spelling of a version into the PEP 440 one.

    `0.1.0~beta25` -> `0.1.0b25`; a plain `0.1.0` passes through.
    """
    release, _, prerelease = version.partition("~")
    if not prerelease:
        return release
    match = re.fullmatch(r"([a-z]+)\.?(\d+)", prerelease)
    if match and match.group(1) in _PRERELEASE_TAGS:
        return f"{release}{_PRERELEASE_TAGS[match.group(1)]}{match.group(2)}"
    raise ValueError(
        f"cannot express {version!r} in PEP 440: expected a prerelease of "
        f"the form ~alpha<N>, ~beta<N> or ~rc<N>"
    )


PEP440_VERSION = _to_pep440(VERSION)

"""The single source of the Kanfei version string.

`VERSION` lives in a plain text file beside this module rather than in
Python, because `debian/changelog` and the frontend build both need the
same value and neither can import Python.  The file ships inside
`backend/app/`, which `debian/rules` already copies wholesale, so an
installed package carries it without a packaging change.

Bump `backend/app/VERSION` and `debian/changelog` together at release —
`tests/backend/test_version.py` fails if they disagree.
"""

from pathlib import Path

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()

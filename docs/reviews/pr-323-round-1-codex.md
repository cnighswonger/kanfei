# Review: PR 323 release-review beta28 bump

Date: 2026-08-13
Reviewed: PR 323 at cd845af36804b4634e885bc0a472cb2b1f096302
Round: 1
Label applied: changes-requested

## What Is Correct

The runtime version, public API documentation example, and Debian
changelog header all use the canonical Debian version string
`0.1.0~beta28`.

The version-drift audit found no stale current-version literals outside
allowed historical references. Remaining `beta27` hits are historical
test/comment references, and the only `beta28` literals outside the
changelog are `backend/app/VERSION` and the public weather schema
example.

The changelog scope matches the material beta28 release surface. IDENT
product SKU, RX Diagnostics, the wire-audit script, and the fw 4.33
wire-audit documentation are covered. The OPMODE endpoint does not need
a separate user-facing bullet because the release-visible surface is the
RX Diagnostics tile that consumes it.

`dpkg-parsechangelog` parses the new entry, and the bullet indentation
and wrapping match the existing changelog voice and format.

Local verification passed:

```text
cd backend && python3 -m pytest ../tests/backend/test_version.py -q
13 passed in 0.06s
```

## Blockers

### `debian/changelog:40` has the wrong weekday for the release date

The trailer currently says:

```text
 -- Chris Nighswonger <dev@veritassuperaitsolutions.com>  Wed, 13 Aug 2026 00:20:00 +0000
```

August 13, 2026 is a Thursday, not a Wednesday. Debian tooling accepts
the entry, but the release metadata is internally inconsistent. That is
release-facing metadata and should be corrected before tagging or
building beta28.

Expected shape:

```text
 -- Chris Nighswonger <dev@veritassuperaitsolutions.com>  Thu, 13 Aug 2026 00:20:00 +0000
```

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

Fix only the weekday in the beta28 changelog trailer, then rerun the
version tests. No changelog copy expansion is needed for OPMODE; the
current RX Diagnostics bullet accurately covers its user-visible role.

## Bottom Line

Request changes. The version bump itself and release scope look right,
but the changelog trailer has incorrect date metadata for the release.

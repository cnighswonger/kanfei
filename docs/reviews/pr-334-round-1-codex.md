# Review: PR 334 release-review beta30 bump

Date: 2026-08-13
Reviewed: PR 334 at 1f47f7ee5a84ebff43e283974752c73f3b295667
Round: 1
Label applied: changes-requested

## What Is Correct

The release bump uses the canonical Debian version string
`0.1.0~beta30` in the runtime version file, the public weather schema
example, and the new Debian changelog header.

The version-drift audit found no stale tracked `0.1.0~beta29` or
`0.1.0-beta29` literals outside the allowed historical changelog entry,
and no non-canonical beta30 spelling such as `0.1.0-beta30` or
`0.1.0.beta30`.

The beta30 changelog scope matches the material commits since
`v0.1.0-beta29`: #329 Solar & UV tile additions, #330 Station Status
battery rows, #331 console sunrise/sunset preference, #332 ET history
columns and migration, and #333 Daily Solar Energy history chart.

The Solar Energy unit set matches the implementation: Settings offers
`MJ/m²`, `kWh/m²`, and `Wh/m²`; the tile and history endpoint display
the operator-selected unit. The battery wording matches the frontend
behavior: transmitter rows show `OK` or `Low: TX1, TX3`, and console
voltage warns below `4.0 V`. The ET migration wording matches the
init-time idempotent backfill from `extra_json` into dedicated columns.
The Daily Solar Energy chart wording matches #333: `/api/history/solar-energy`
returns one local-calendar-day value per day, and the frontend renders a
Highcharts column chart with gaps for missing days.

Debian changelog parsing and version tests passed:

```text
dpkg-parsechangelog -l debian/changelog | head
Version: 0.1.0~beta30
Date: Thu, 13 Aug 2026 21:25:00 +0000

cd backend && python3 -m pytest ../tests/backend/test_version.py -q
13 passed in 0.08s
```

## Blockers

### `debian/changelog:36` describes the astronomy API source marker as the wrong field shape

The beta30 astronomy bullet says:

```text
the response shape gains a "source" field so a consumer can tell which
value came from where.
```

The implementation does not add a field named `source`. It adds two
specific fields on `sun`: `sunrise_source` and `sunset_source`, each
with `"console"` or `"astral"` values. Because the changelog quotes
`"source"` as if it were the API field name, an API consumer reading the
release notes would look for a field that does not exist.

Expected direction: describe the two source markers without implying a
literal `source` field, for example:

```text
the response shape gains sunrise_source and sunset_source markers so a
consumer can tell which displayed value came from where.
```

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

Adjust only the astronomy changelog wording, then rerun the version
tests. The rest of the release metadata, changelog scope, and release
voice look ready.

## Bottom Line

Request changes. The beta30 bump is structurally correct and the release
scope is complete, but the changelog currently documents the new
astronomy source marker with the wrong API field shape.

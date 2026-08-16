# Review: PR 373 fixed persona dashboard layouts round 3

Date: 2026-08-16
Reviewed: PR #373 at 8e30f0be2f8c97077dca2c3e3ef1c0704bd7f199
Round: 3
Label applied: changes-requested

## What Is Correct

- The specific round-2 tile-fit blockers are resolved for the requested desktop slots. At 1920x1080 against the rebuilt PR bundle, `outside-temp` measured `clientHeight=204, scrollHeight=204`, `current-conditions` measured `204/204`, and `almanac` measured `157/157`.
- `station-status` remains clipped by the fixed 145 px slot (`clientHeight=145, scrollHeight=229`), but that matches the round-3 acceptance note that this overflow is deferred until the footer rewrite.
- `tests/e2e/dashboard.spec.ts:16` now uses `[data-dashboard-grid]`, and the targeted smoke check passes: `KANFEI_E2E_PORT=8873 npx playwright test dashboard.spec.ts -g "page loads with dashboard grid" --reporter=line`.
- `tests/e2e/dashboard.spec.ts:82` skips the wind tile display-toggle describe instead of deleting it, preserving the stale edit-mode/layout-persistence coverage as visible follow-up work.
- `cd frontend && npx tsc --noEmit` and `cd frontend && npm run build` both pass. The Vite chunk warning is the repo's known non-blocking warning.

## Blockers

1. `tests/e2e/dashboard.spec.ts` still has active stale dashboard assertions, so the file is not actually green after the fixed-layout pivot. Running `KANFEI_E2E_PORT=8873 npx playwright test dashboard.spec.ts --reporter=line` gives `5 failed / 4 skipped / 6 passed`. The active failures are:

   - `tests/e2e/dashboard.spec.ts:25` expects `70.0°F`, but the fixed dashboard no longer renders that exact inside-temperature text.
   - `tests/e2e/dashboard.spec.ts:41` expects `SW 225°`, but the fixed dashboard does not expose that exact wind direction string.
   - `tests/e2e/dashboard.spec.ts:47` expects `62%`, but the fixed dashboard does not expose that exact outside-humidity text.
   - `tests/e2e/dashboard.spec.ts:64` expects `H 81°` / `L ...` on the outside-temp tile, but those exact strings are no longer found.
   - `tests/e2e/dashboard.spec.ts:70` expects no `W/m²`, but the fixed layout renders the solar/UV slot with that unit.

   Round 3 fixed the startup selector failure and skipped the removed edit-mode block, but the remaining active tests still assert old dashboard surface details. This needs either updated assertions for the fixed-layout contract or explicit skipping of stale cases with the same rationale used for the wind block.

## What Needs Attention

- `frontend/src/components/tiles/AlmanacTile.tsx:8` still fetches station status and stores it in state even though the Station row was removed and the value is immediately voided at `frontend/src/components/tiles/AlmanacTile.tsx:31`. This is not a merge blocker, but it is now dead request/state work and should be removed when the tile is touched next.

## Bloat / Non-Functional

None blocking.

## Recommendations

- Keep the passing selector smoke test, then update the rest of the active `Dashboard` describe to assert what the fixed layout actually promises: slot presence, data-tile ids, and current visible values that still exist in the redesigned tiles.
- Remove the dead station-status fetch from `AlmanacTile` as a small cleanup alongside the e2e adjustment if it stays in this PR.

## Bottom Line

Request changes. The tile clipping fix is good for the requested target tiles, and type/build verification is clean, but the dashboard e2e spec still has five active failing tests. I cannot approve while the changed spec file remains red outside the narrow grep.

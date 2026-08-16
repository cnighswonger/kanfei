# Review: PR 373 fixed persona layouts round 2

Date: 2026-08-16
Reviewed: PR #373 at 6058237b4aee58bbca1cec88634292575413b43e
Round: 2
Label applied: changes-requested

## What Is Correct

- `EverydayDashboard` now wraps the full dashboard `<main>` in `CompactProvider`, so nested grid and flex descendants that call `useCompact()` receive `useIsMobile()` instead of the context default.
- The deleted mobile CSS rules for `.dashboard-grid` and `.dashboard-toolbar` are no longer referenced from `frontend/src` JSX/CSS, and `.dashboard-heading` has a mobile rule again for `History.tsx`.
- `frontend/src/utils/uiPrefs.ts` no longer seeds or migrates the old frontend dashboard layout preference keys.
- `npx tsc --noEmit` and `npm run build` both pass. The Vite chunk-size warning is the repo's known non-blocking warning.

## Blockers

1. `overflow: hidden` is clipping visible desktop tile content, not just containing an over-tall station-status tile.

   `frontend/src/dashboard/layouts/EverydayDashboard.tsx:36` defines the slot contract as fixed height plus `overflow: "hidden"` at `frontend/src/dashboard/layouts/EverydayDashboard.tsx:57`. Against the rebuilt PR bundle at a 1920x1080 viewport, the intended tile slots measured:

   - `outside-temp`: `clientHeight=204`, `scrollHeight=269`, clipped by 65 px
   - `current-conditions`: `clientHeight=204`, `scrollHeight=211`, clipped by 7 px
   - `almanac`: `clientHeight=157`, `scrollHeight=200`, clipped by 43 px
   - `station-status`: `clientHeight=145`, `scrollHeight=229`, clipped by 84 px

   This satisfies the overlap stopgap but fails the requested round-2 verification that the ten intended renders are not clipping user-visible content at their design heights. The station-status item is the known pressure point, but the same slot-level rule also clips the hero and almanac paths.

2. Dashboard E2E coverage is still targeting removed behavior and now fails at startup.

   `tests/e2e/dashboard.spec.ts:16` still expects `.dashboard-grid`, but the PR removes that class and only renders `data-dashboard-grid` in `frontend/src/dashboard/layouts/EverydayDashboard.tsx:73`. Running `KANFEI_E2E_PORT=8873 npx playwright test dashboard.spec.ts -g "page loads with dashboard grid"` fails with `element(s) not found` for `locator('.dashboard-grid')`.

   The same spec also keeps the removed layout preference flow alive at `tests/e2e/dashboard.spec.ts:90`, `tests/e2e/dashboard.spec.ts:200`, and `tests/e2e/dashboard.spec.ts:238` by writing/reading `ui_dashboard_layout`. Since the fixed persona layout removed the edit-mode/layout persistence surface, these tests need to be deleted or rewritten to the new fixed-layout contract before this PR is mergeable.

## What Needs Attention

- `backend/app/api/config.py:142` still documents and defaults `ui_dashboard_layout` plus the per-persona layout keys. If the intent is to remove those keys repo-wide, backend defaults remain a live producer of them. If backend compatibility is intentionally deferred, call that out explicitly so this does not look like an incomplete frontend-only cleanup.

## Bloat / Non-Functional

None.

## Recommendations

- Fix tile fit before relying on slot clipping: either reduce the affected desktop tile content to the fixed design heights or adjust the layout heights so `scrollHeight <= clientHeight` for every intended slot.
- Update `tests/e2e/dashboard.spec.ts` to use `[data-dashboard-grid]` / `[data-tile-id]` for the fixed layout and remove edit-mode persistence tests that no longer map to product behavior.
- Decide whether backend config layout defaults are retained compatibility surface or dead defaults, then document or remove accordingly.

## Bottom Line

Revise. Round 2 restores compact context and cleans the CSS/frontend pref items, but the slot clipping verification fails empirically and the dashboard E2E suite still asserts removed selectors and removed layout persistence.

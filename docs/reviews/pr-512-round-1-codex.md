# Review: PR 512 Agriculture Tablet Middle Tier

Date: 2026-08-27
Reviewed: `feature/mobile-4a-tablet-agriculture` at `1d8f52c5b6a5e4516fcecdb320278aba0e4fab16`
Round: 1
Label applied: `changes-requested`

## What Is Correct

The hook shape matches `useIsMobile`: lazy `matchMedia`, a `change` listener, and cleanup. In this SPA/Vite app there is no SSR path for this component tree, so the direct `window.matchMedia()` initializer is consistent with the existing mobile hook.

The breakpoint math itself has no gap or overlap: `useIsMobile` owns `max-width: 768px`; `useIsTablet` owns `min-width: 769px` through `max-width: 1213px`; the desktop branch resumes at `1214px`.

The new shell follows the phase 3b/3c mobile-shell primitives where intended: it returns before the desktop scaled composition, publishes `data-tablet`, hoists `--k` and `--kt` to `1px`, and leaves the reused tile bodies unmodified. Dropping the Agriculture plate in this shell is also reasonable: this branch bypasses the desktop `scaleVar(928)` frame that positions the plate, and the supplied 768 mock shows flat ground.

## Blockers

1. `frontend/src/dashboard/AgricultureDashboard.tsx:981` starts the tablet shell at the viewport breakpoint, but the app shell brings back the fixed 220px desktop sidebar at the same `769px` boundary. That means the new two-column grid does not actually have a 769px content frame at the lower end of the tier. In a production-build browser probe at `769x1024`, the Agriculture dashboard rendered with `data-tablet`, but its content box was only 549px wide after the sidebar, and the dashboard had horizontal overflow (`clientWidth=549`, `scrollWidth=611`). The visible result is clipped content in the first rows: the forecast tile's "Next window" value is cut off at the right edge, and the drift-risk tile's right-side readout is clipped offscreen.

   This is caused by combining the fixed two-column split at `frontend/src/dashboard/AgricultureDashboard.tsx:981` / `:987` with reused desktop tile internals that still require more width than those columns provide. The verdict tile is one concrete example: `frontend/src/dashboard/AgricultureDashboard.tsx:260` pins the verdict slot to `minWidth: st(240)`, and at the `769px` app viewport each tablet column is only about 241px before the tile's own padding and internal flex gap. The drift tile similarly carries a 250px wind rose plus a readout column. This directly violates the phase's "reuse unmodified tiles inside a 2-col grid" safety condition for the lower part of the stated `769-1213` tier.

## What Needs Attention

The browser probe showed the overflow clearing at the dashboard level by wider tablet widths, but the bottom of the tier is still part of the advertised contract. The fix should make the breakpoint account for the available dashboard content width, or keep the mobile/overlay shell active until the two-column tablet shell has enough space for these reused tile bodies. A container-based decision would match the actual failure mode better than another viewport-only number, but the key requirement is that `769px` through the chosen lower bound must not enter this two-column reused-tile shell while the desktop sidebar is consuming 220px.

## Bloat / Non-Functional

None. The change is small and follows the existing direct-shell pattern; the problem is breakpoint/content-width correctness, not unnecessary abstraction.

## Recommendations

Retest the corrected version at the branch boundaries and near the lower tier: `768`, `769`, `800`, `850`, `900`, `1213`, and `1214` viewport widths. Include the real app shell in that check, because the sidebar is the load-bearing constraint here.

## Bottom Line

Revise before merge. The hook and branch ordering are internally consistent, and the plate-off decision is fine, but the new tablet branch currently activates in a real app layout where the reused desktop Agriculture tiles do not fit.

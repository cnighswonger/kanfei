# Review: PR #373 fixed persona dashboard layouts

Date: 2026-08-16
Reviewed: `frontend/src` changes at `413324f5883bfdd52f6a5a149393a0f6bde2a002`
Round: 1
Label applied: changes-requested

## What Is Correct

- No dangling references remain in `frontend/src` for the deleted drag-grid modules or removed placement exports named in the review request. `npx tsc --noEmit` also passes.
- The direct gauge prop wiring in `EverydayDashboard.tsx` matches the receiving component prop contracts for `BarometerDial`, `WindCompass`, `RainGauge`, and `SolarUVGauge`.
- `HeroTemperatureTile`, `CurrentConditions`, `StationStatus`, `RainHourlyTile`, `AlmanacTile`, and `HistoryChartTile` are imported and rendered consistently with their current self-fetching/context-fetching contracts.
- The persona switch currently routes every persona to `EverydayDashboard`; that is an intentional scaffold per the nearby comment, though it can be simplified until the other layout components exist.

## Blockers

1. `frontend/src/dashboard/layouts/EverydayDashboard.tsx:143` puts `StationStatus` in a fixed 145 px slot, but `StationStatus` still renders its full desktop status panel when `useCompact()` is false and its root does not set `height: "100%"` or constrain overflow. The desktop panel includes the station clock row plus a two-column grid of many status rows, so it cannot fit in 145 px. Because the `Slot` wrapper at `frontend/src/dashboard/layouts/EverydayDashboard.tsx:49` only sets `height` and leaves overflow visible by default, the panel will paint outside the slot instead of honoring the fixed layout. This breaks the literal fixed-height composition and likely overlaps/extends past band B. The fixed layout needs either a compact/footer-specific station status rendering, a real height/overflow contract, or a slot height that matches the desktop content.

2. Mobile compact mode is broken by the `CompactProvider` removal. `CompactContext` defaults to `false` at `frontend/src/dashboard/CompactContext.tsx:3`, and the new dashboard never provides a value, while `EverydayDashboard` hard-codes the desktop two-column grid and fixed desktop dimensions at `frontend/src/dashboard/layouts/EverydayDashboard.tsx:28`, `frontend/src/dashboard/layouts/EverydayDashboard.tsx:62`, `frontend/src/dashboard/layouts/EverydayDashboard.tsx:71`, and `frontend/src/dashboard/layouts/EverydayDashboard.tsx:143`. Components such as `BarometerDial` branch to compact rendering only when `useCompact()` is true (`frontend/src/components/gauges/BarometerDial.tsx:46` and `frontend/src/components/gauges/BarometerDial.tsx:53`), so mobile now gets desktop gauge variants with large SVGs inside a desktop grid. Before this PR, `DashboardGrid` supplied compact mode on mobile and for narrow tiles. Please restore an explicit mobile/narrow layout strategy or intentionally remove the compact branches with equivalent responsive behavior.

## What Needs Attention

- The old dashboard layout keys are still part of `UI_DEFAULTS` in `frontend/src/utils/uiPrefs.ts:24`, and `syncUIPrefs()` still writes them back to localStorage at `frontend/src/utils/uiPrefs.ts:161` and reads them on fallback at `frontend/src/utils/uiPrefs.ts:173`. I did not find a dashboard consumer of those values, but the claim that no code path reads the layout keys is not currently true. If these keys are dead after the fixed-layout pivot, remove them from the frontend preference defaults and reconcile whether backend defaults/config rows should be cleaned in a separate migration.
- `frontend/src/pages/History.tsx:288` still uses `className="dashboard-heading"`. The deleted mobile CSS rule for `.dashboard-heading` may have been intended only for the old dashboard edit heading, but the class name is not fully unused in JSX.

## Bloat / Non-Functional

None.

## Recommendations

- Make slot sizing a real contract: repeated card components either need `height: "100%"` when used in fixed slots, or the slot wrapper should deliberately clip/scroll where Design requires a fixed height. Do not rely on parent `height` alone; visible overflow defeats the fixed layout.
- Replace the all-branches-same persona ternary with `const Layout = EverydayDashboard;` until the Agriculture and Weather Nerd layout components land. The comment already preserves the scaffold intent.

## Bottom Line

Request changes. The deletion/refactor is mostly clean and type-safe, but fixed-height composition and mobile compact behavior are not yet preserved by the new literal layout.

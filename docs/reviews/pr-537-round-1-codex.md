# Review: PR #537 Nerd chart left-axis padding

Date: 2026-08-30
Reviewed: `frontend/src/dashboard/WeatherNerdDashboard.tsx` at `1213d23f894d7c707f1778b48c0399bf8079a258`
Round: 1
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

The change is scoped to the left-axis label padding in `NerdChartTile`.
Desktop rendering is unchanged because the non-compact branch still resolves to `s(8)`.

At compact widths, the left-axis span remains anchored at `left: 0` with width
`PL / CW`; `boxSizing: 'border-box'` means increasing `paddingRight` only moves
the right-aligned label text farther left inside the existing axis band. It does
not widen the band, move the plot rectangle, or push labels into the plot.

The emphasized whole-inch gridline path is unaffected. Its rendering still
depends on `stripWhole && bp && right.filter((g) => g.whole)`, and its x-range
remains `PL + GRID_INSET` through `CW - PR - GRID_INSET`. The padding change
does not alter `stripWhole`, right-axis tick generation, gridline selection, or
gridline coordinates.

Verification run:

- `cd frontend && npx tsc --noEmit` passed.
- `cd frontend && npm run build` passed. Vite emitted the known chunk-size
  warning, which this repo documents as non-blocking.
- `cd tests/e2e && KANFEI_E2E_PORT=8875 npx playwright test dashboard.spec.ts --project=chromium`
  started the app but failed before finding `[data-dashboard-grid]`; the first
  attempt also hit the default port already in use. Those failures prevented a
  browser-based visual assertion for this review and appear unrelated to this
  one-line axis padding change.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

No changes requested.

## Bottom Line

Approve. The compact-only padding bump addresses the commissioned visual gap
without changing desktop behavior, plot geometry, right-axis labeling, or the
whole-inch emphasized gridline mechanics.

— Codex, cross-LLM review, round 1

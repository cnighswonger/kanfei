# Review: PR #536 Nerd Chart Plot Tint

Date: 2026-08-29
Reviewed: `frontend/src/dashboard/WeatherNerdDashboard.tsx` at `8eb22808371628f07e58306f4c12f15da4359adf`
Round: 1
Label applied: `approved-by-codex-agent`

## What Is Correct

The change moves the Nerd chart tint from the wrapper `<div>` to the SVG plot area only. The new `<rect>` in `frontend/src/dashboard/WeatherNerdDashboard.tsx:561` uses `x={PL}`, `y={PT}`, `width={CW - PL - PR}`, and `height={CH - PT - PB}`, matching the intended `[PL, CW-PR] × [PT, CH-PB]` plot rectangle.

The fill still uses `v.chart.surface`, so the plot-area color matches the prior wrapper background token at desktop. The wrapper no longer owns that background, which means the left, right, and bottom HTML axis-label bands sit on the tile paper instead of the chart tint.

The rect is the first SVG child before gridlines and traces, so the rendered ordering is correct: gridlines, pressure, dew point, temperature, and the baseline paint over the tint.

I checked other `v.chart.surface` uses in the frontend. The only wrapper background removed by this PR is this Nerd chart wrapper; the remaining uses are in other chart components or marker fills and do not depend on this wrapper carrying the tint.

Verification passed:

```bash
cd frontend && npx tsc --noEmit
```

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

None.

## Bottom Line

Approve. The implementation is narrowly scoped and satisfies the requested behavior: plot tint remains in the plot rectangle, phone axis-label bands are no longer tinted, and traces render above the tint.

— Codex, cross-LLM review, round 1

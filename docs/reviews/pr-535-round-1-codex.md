# Review: PR #535 Nerd chart compact pressure labels

Date: 2026-08-29
Reviewed: PR #535 diff at `41b45353a038d127a9de3369b63faa555362cca1`
Round: 1
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

The pressure axis right padding is restored to `PR = 52` unconditionally in `frontend/src/dashboard/WeatherNerdDashboard.tsx`, so desktop and tablet render geometry returns to the pre-#534 behavior. The compact-only label shortening is gated by `compact && pu !== 'hPa'`, which keeps hPa labels full while trimming inHg labels from values such as `30.20` and `29.95` to `.20` and `.95`.

The emphasized whole-inch gridline is conditionally rendered only when labels are stripped, uses `stroke={v.chart.trace}`, `strokeWidth={1.2}`, and `opacity={0.35}`, and appears before `<path d={bp.line}>` in SVG source order. That means the pressure trace paints over the guide line, not under it.

The whole-inch detection is tied to actual tick values with `val === Math.round(val)`. Because `niceTicks()` rounds outputs to six decimals, whole ticks such as `30.00` compare cleanly.

The compact inHg labels are now three-character hundredths labels. With `PR = 52`, the right band is still about 7.9% of the chart wrapper, but `.20`/`.95` are materially narrower than `30.20`/`29.95` and satisfy the intended phone-width fit without moving the plot boundary inward.

Regex behavior was checked directly: `/^\d+\./` converts `30.20` to `.20`, `29.95` to `.95`, and `0.05` to `.05`; signed negatives such as `-29.95` are left unchanged. That is acceptable here because pressure values are positive-domain data, and adding defensive formatting for impossible negative pressure would not improve this UI path.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

No code changes recommended for this round.

## Verification

Ran `npx tsc --noEmit` from `frontend`; it passed. Also checked the label-stripping regex behavior with Node for positive and signed sample strings.

## Bottom Line

Approve. The PR restores the previous chart geometry outside compact mobile rendering, solves the narrow inHg label band by shortening only compact inHg labels, and keeps the new emphasized whole-inch guide line visually behind the pressure trace.

— Codex, cross-LLM review, round 1

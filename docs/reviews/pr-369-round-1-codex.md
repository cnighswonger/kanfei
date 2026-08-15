# Review: PR 369 ui dashboard composition gauges

Date: 2026-08-15
Reviewed: PR #369 at 7224793a3e64f13d1d7805765213e320e52730a1
Round: 1
Label applied: changes-requested

## What Is Correct

The composition pinning path is mostly sound. `gridColStart` and `gridRowStart`
are preserved by `parseLayout` because the validation path filters only unknown
tile IDs and returns the surviving placement objects intact. Reset-to-default
therefore saves the pinned defaults, and reload preserves them. The mobile guard
is also reasonable: explicit grid placement is desktop composition, while mobile
keeps the existing auto-flow behavior with effective 6-column spans.

`stripPins` does strip the fields at runtime. The destructuring rest object drops
`gridColStart` and `gridRowStart`; the `_c` / `_r` bindings also pass this
branch's strict TypeScript build.

The ledger overlay is positioned behind the Highcharts container and uses
`pointerEvents: "none"`, so it should not block chart hover/click interaction.
With the chart container at `zIndex: 1`, Highcharts content and tooltips remain
above the overlay.

## Blockers

1. `frontend/src/components/gauges/BarometerDial.tsx:70` passes the display
   value directly into `wheelDial`, but `wheelDial` is explicitly fixed to a
   28.5-31.0 inHg range in `frontend/src/utils/gauges.ts:54`. If this component
   receives hPa, as its public props and the site unit model allow, a normal
   value such as 1013 hPa clamps the needle to the maximum end of the dial while
   the readout says `1013 hPa`. The zone sentence has the same problem at
   `frontend/src/components/gauges/BarometerDial.tsx:212`: `zoneFor` receives
   the hPa value and reports `set fair` for essentially every normal pressure.
   The old component had separate hPa ranges, so this is a regression for
   metric-pressure users. Convert hPa/mb to inHg before feeding the dial and
   zone logic, or render a unit-appropriate dial.

2. `frontend/src/components/gauges/BarometerDial.tsx:141` always renders the pale
   trend hand, but the geometry is a hard-coded `frac - 0.12` in
   `frontend/src/utils/gauges.ts:88`, not the previous pressure or the supplied
   `trendRate`. That means even `trend={null}` or a steady/rising pressure gets
   a visible historical hand that implies a fixed prior higher pressure. Either
   derive the trend-hand value from real trend data, or hide the trend hand when
   the data is unavailable.

## What Needs Attention

`frontend/src/components/gauges/WindCompass.tsx:58` calls `rosePetals()` without
weights, so `frontend/src/utils/gauges.ts:120` uses the built-in WSW-heavy demo
distribution. The PR body says the compass has a "wedge distribution under the
ring"; if this is intentionally decorative, say that explicitly in the PR body
and consider reducing the data-like visual weight. As rendered, it looks like
real wind distribution on a weather dashboard while being unrelated to the
station data.

## Bloat / Non-Functional

None.

## Recommendations

Keep the explicit-positioning behavior as-is: desktop pins solve the composition
problem, and dropping them on user edits avoids a confusing drag experience.

Consider adding a small unit test for the pressure conversion edge case around
`BarometerDial`/`wheelDial` if gauge geometry stays as pure functions.

## Bottom Line

Request changes. The layout persistence and pin stripping check out, and the
build passes, but the barometer rewrite currently displays misleading analog
state for hPa/mb inputs and for missing or non-falling trend data.

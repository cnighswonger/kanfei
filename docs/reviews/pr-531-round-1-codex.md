# Review: PR #531 mobile shell padding

Date: 2026-08-27
Reviewed: `feature/mobile-widen` at `64be35697609879fdead890e92dda9cd4d0d0919`
Round: 1
Label applied: `approved-by-codex-agent`, `reviewed-by-codex-agent`

## What Is Correct

The diff is limited to the three phone shell wrappers:

- `frontend/src/dashboard/EverydayDashboard.tsx`
- `frontend/src/dashboard/AgricultureDashboard.tsx`
- `frontend/src/dashboard/WeatherNerdDashboard.tsx`

Each changed wrapper is selected only through the `useIsMobile()` branch before the tablet branch runs, so tablet and desktop render paths keep their existing shell padding and layout code.

The Everyday high/low `MChip` pair still has enough width at a 360 px viewport after the padding change. The content width becomes `360 - 12 - 12 = 336`; the two-column chip grid leaves `(336 - 12 gap) / 2 = 162` px per chip. After the chip's internal `10px` side padding, about 142 px remains for the `High` or `Low` label, the `8px` flex gap, and a short Fahrenheit value. The chip content is baseline-aligned with `justifyContent: 'space-between'`, so the pair should not wrap at the reviewed width.

The only active 328 px literal I found in these shells is the agriculture mobile forecast strip's SVG viewBox width (`const W = 328`). Because the SVG renders with `width: '100%'` and `preserveAspectRatio="none"`, the wider 336 px shell stretches the strip rather than creating a stale fixed-width overflow. The other 328 px references in the reviewed files are comments documenting prior phone-width constraints.

Verification run:

- `cd frontend && npx tsc --noEmit` passed.

## Blockers

None.

## What Needs Attention

None.

## Bloat / Non-Functional

None.

## Recommendations

No follow-up required for this PR.

## Bottom Line

Approve. This is a narrowly scoped phone-shell padding adjustment; the reviewed tablet/desktop paths are untouched, the Everyday `MChip` pair still fits at the new 336 px content width, and the remaining active 328 px mobile strip width scales through the SVG/viewBox boundary instead of assuming a fixed rendered width.

— Codex, cross-LLM review, round 1
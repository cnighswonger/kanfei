# Review: PR 520 mobile double scrollbar and themed scrollbar

Date: 2026-08-27
Reviewed: `frontend/src/components/layout/AppShell.tsx`, `frontend/src/index.css` at `d77b77168f055cb4ed465d969d51cf453a0fc1bf`
Round: 1
Label applied: changes-requested

Codex review: Round 1 review of PR 520.

## What Is Correct

- The `100vh` to `100dvh` change on the AppShell root grid addresses the right mobile failure mode. Current compatibility data supports `dvh` in Safari 15.4+, Chrome/Edge 108+, Firefox 101+, and Samsung Internet 21+; older mobile browsers and old WebViews would ignore a bare `dvh`, but that is only a support concern if Kanfei needs to keep those clients working. The PR body's Firefox 118+ minimum is too conservative; Firefox shipped these viewport-unit variants earlier.
- `body.settings-scroll-lock { overflow: hidden; }` is not functionally affected by the global scrollbar styling. When overflow is hidden, the scrollbar is not painted.
- The theme token dependency is present. `ThemeContext.applyThemeToDOM()` maps `surfaceSunken`, `textMuted`, and `accent` to `--color-surface-sunken`, `--color-text-muted`, and `--color-accent`; all built-in themes define those color fields. The new CSS uses `--color-sunken`, not `--color-surface-sunken`, but every current built-in theme has `bgSecondary === surfaceSunken`, and the older scrollbar block already uses `--color-bg-secondary` for the track.
- Remaining `100vh` references under `frontend/src/` are limited to the setup-loading screen, the login screen, and dashboard scaling formulas. Those may still have local mobile URL-bar sizing behavior, but they do not recreate the shell/body double-scrollbar symptom this PR targets.
- `npx tsc --noEmit` passes.

## Blockers

1. `frontend/src/index.css:86` adds the new WebKit scrollbar styling before the pre-existing global WebKit scrollbar block at `frontend/src/index.css:143`. Because the later `::-webkit-scrollbar-track`, `::-webkit-scrollbar-thumb`, and `::-webkit-scrollbar-thumb:hover` rules have the same effective specificity and come later in the cascade, Chrome/Safari keep the old track/thumb/hover colors instead of the new `--color-sunken` / `--color-text-muted` / `--color-accent` palette. Firefox gets the new `scrollbar-color`, but the WebKit half of the advertised fix is largely overridden. Remove or merge the older block, or move the intended final rules after it, so Chromium/WebKit mobile actually render the themed scrollbar this PR claims.

## What Needs Attention

- The new comments in both changed files are much longer than the code they explain and include task-specific provenance such as the operator's v55 report. The underlying `dvh` reason is useful, but this should be shortened to a durable CSS note once the functional blocker is fixed.

## Bloat / Non-Functional

- The duplicate global scrollbar blocks are now both a functional bug and unnecessary CSS. One canonical block is enough.

## Recommendations

- Keep the `dvh` changes.
- Consolidate scrollbar styling into one global WebKit block, then ensure Firefox and Chromium/WebKit read the same intended theme tokens.
- If supporting pre-Samsung Internet 21, pre-Chrome 108 WebViews, or pre-iOS 15.4 Safari matters, use a fallback pair such as `height: 100vh; height: 100dvh;` and matching `min-height` declarations. If Kanfei's target is current operator devices only, the bare `dvh` change is acceptable.

## Bottom Line

Revise before merge. The viewport-height fix is sound, but the new themed scrollbar rules do not take effect in Chrome/Safari because the old global WebKit scrollbar block later in `index.css` overrides them.

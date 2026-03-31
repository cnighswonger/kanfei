# Project: Kanfei

Self-hosted weather station dashboard and data logger for personal weather stations. FastAPI backend with React/TypeScript frontend.

## Build

- Frontend: `cd frontend && npm run build`
- Backend: Python 3.10+, dependencies in `backend/pyproject.toml`
- Tests: `cd backend && python -m pytest ../tests/backend/ -q`
- Debian package: `dpkg-buildpackage -us -uc -b` from repo root (on `deb` branch)
- CLI: `python station.py setup | run | dev | test | backup | restore | clean | status`

## Git Workflow

- **Main branch**: `origin/main` — primary development target
- **Feature branches**: `feature/*` — branch from main, open PR, merge via PR, delete branch
- **E2E branches**: `feature/e2e/*` or `fix/e2e/*` — for changes requiring E2E testing (UI behavior changes). Run `./scripts/e2e-report.sh` and post results to PR before review.
- **Fix branches**: `fix/*` — for bugfixes
- **Debian packaging branch**: `deb` — package build files
- Small changes can go directly to main; larger work should use branches + PRs
- **GitHub release filenames**: GitHub converts `~` to `.` in uploaded asset filenames

## Coding Discipline

- **Do not expose kanfei-nowcast internals** in this public repo — no prompt section names, detection algorithms, or architecture details in issues or code comments. Describe only user-visible symptoms and outcomes.
- Prefer editing existing files over creating new ones
- Run `npx tsc --noEmit` before committing frontend changes
- Vite chunk size warnings ("Some chunks are larger than 500 kB after minification") are **non-blocking** — the build still succeeds. Do not treat these as errors or attempt to fix them unless explicitly asked.
- Run `py_compile` on modified Python files before committing
- Run backend tests before committing backend changes
- localStorage migration keys (`davis-wx-*` in `uiPrefs.ts`) are intentional for backwards compatibility — do not remove
- Mark beta releases as full releases (not prerelease) so they show on the landing page
- Multi-phase issues: use `Ref #N` (not `Closes #N`) until the final phase PR

## Pre-Work

- **Step 0 cleanup**: Before any structural refactor on a file >300 LOC, first remove dead props, unused exports, unused imports, and debug logs. Commit this cleanup separately before the real work. Dead code wastes context tokens and accelerates compaction.
- **Phased execution**: For multi-file refactors, break work into explicit phases. Complete a phase, run verification, and get approval before the next. Phases should be scoped by complexity, not an arbitrary file count — mechanical changes across many files (e.g., adding an import to 14 routers) are fine in one pass; complex logic changes should be phased.

## Code Quality

- **Flag architectural issues, don't silently refactor.** If architecture is flawed, state is duplicated, or patterns are inconsistent — flag it and propose a fix. Do not unilaterally refactor beyond the current task scope. The user decides whether to expand scope.
- **Forced verification**: Do not report a task as complete until you have:
  - Run `npx tsc --noEmit` (frontend)
  - Run `py_compile` on modified Python files (backend)
  - Run `python -m pytest tests/backend/ -q` (backend changes)
  - Fixed ALL resulting errors
  - If no type-checker or test runner applies, state that explicitly instead of claiming success.

## Context Management

- **Sub-agent usage**: For tasks touching many independent files, consider launching parallel sub-agents. Each agent gets its own context window. Use this for genuinely independent work (research, mechanical edits across many files), not for interconnected changes that need shared context.
- **Context decay awareness**: After 10+ messages or any auto-compaction, re-read any file before editing it. Do not trust memory of file contents — compaction may have silently dropped that context. Editing against stale state causes silent failures.
- **File read budget**: File reads are capped at 2,000 lines. For files over 500 LOC, use offset and limit parameters to read in sequential chunks. Never assume a complete file was seen from a single read.
- **Tool result blindness**: Large tool results are silently truncated to a preview. If any search or command returns suspiciously few results, re-run with narrower scope (single directory, stricter glob). State when truncation is suspected.

## Edit Safety

- **Edit integrity**: Before every file edit, re-read the file. After editing, verify the change applied correctly if the edit was complex. The Edit tool fails silently when `old_string` doesn't match due to stale context. Do not batch more than 3 edits to the same file without a verification read.
- **No semantic search**: You have grep, not an AST. When renaming or changing any function/type/variable, search separately for:
  - Direct calls and references
  - Type-level references (interfaces, generics)
  - String literals containing the name
  - Dynamic imports and require() calls
  - Re-exports and barrel file entries
  - Test files and mocks
  Do not assume a single grep caught everything.

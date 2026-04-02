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

## Work Discipline (all agents)

- **Step 0 cleanup**: Before any structural refactor on a file >300 LOC, first remove dead code, unused imports, and debug logs. Commit cleanup separately before the real work.
- **Phased execution**: For multi-file refactors, break work into explicit phases. Complete a phase, run verification, and get approval before the next. Scope phases by complexity, not arbitrary file count.
- **Flag architectural issues, don't silently refactor.** If architecture is flawed or patterns are inconsistent — flag it and propose a fix. Do not unilaterally refactor beyond the current task scope. The user decides whether to expand scope.
- **Forced verification**: Do not report a task as complete until the relevant checks pass:
  - Frontend: `npx tsc --noEmit`
  - Backend: `py_compile` + `python -m pytest tests/backend/ -q`
  - If verification is not possible, state that explicitly.
- **No semantic search**: grep is not an AST. When renaming or changing any function/type/variable, search separately for: direct calls, type-level references, string literals, dynamic imports, re-exports, barrel file entries, and test files/mocks. Do not assume a single search caught everything.
- **Edit with caution after long conversations**: Context may have been compacted. Re-read files before editing if the conversation is long or has been resumed.

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

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
- Run `py_compile` on modified Python files before committing
- Run backend tests before committing backend changes
- localStorage migration keys (`davis-wx-*` in `uiPrefs.ts`) are intentional for backwards compatibility — do not remove
- Mark beta releases as full releases (not prerelease) so they show on the landing page
- Multi-phase issues: use `Ref #N` (not `Closes #N`) until the final phase PR

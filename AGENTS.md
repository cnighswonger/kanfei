# Project: Kanfei

Self-hosted weather station dashboard and data logger for personal weather
stations. FastAPI backend with React/TypeScript frontend.

This file is the single source of standards for every agent working in this
repo — Claude Code, Codex, Gemini, or any other. `CLAUDE.md` is a symlink to
it for Claude Code's auto-discovery; edit this file, never the symlink.

**Structure.** The block between `<!-- BEGIN CANONICAL -->` and
`<!-- END CANONICAL -->` is owned by `vsits/vsits-org-policy` and is
refreshed mechanically by `bin/pull-canonical-agents-md.sh` from that repo.
Do not edit inside the markers — changes there are overwritten on the next
refresh; propose them upstream instead. Everything below `END CANONICAL` is
the Kanfei overlay and is ours to edit freely.

<!-- BEGIN CANONICAL -->
<!-- Everything between BEGIN CANONICAL and END CANONICAL is owned by vsits/vsits-org-policy and refreshed via `bin/pull-canonical-agents-md.sh`. Do not edit in-repo — propose changes upstream. Project-specific overlays live OUTSIDE these markers (above BEGIN or below END). -->

# AGENTS.md — generic coding standards for AI agents

Canonical cross-repo standard for AI agents (Claude Code, Codex, Gemini, others) writing code in any project. `CLAUDE.md` is a symlink to this file for Claude Code's auto-discovery.

This file is project-agnostic on purpose. Project-specific glue (build commands, bot identities, label state machines, deployment paths) belongs in the consuming repo's own `AGENTS.md` — as an overlay OUTSIDE the `<!-- BEGIN CANONICAL -->` / `<!-- END CANONICAL -->` markers.

## How to use this file

- **Drop into a new repo:** copy this `AGENTS.md` (markers included) to the repo root, and add a `CLAUDE.md` symlink → `AGENTS.md`. Add project-specific overlays either above `<!-- BEGIN CANONICAL -->` or below `<!-- END CANONICAL -->` — never inside the markers.
- **Refresh an existing consumer:** run `bin/pull-canonical-agents-md.sh <path-to-target-AGENTS.md>` from this repo. The script replaces everything between the markers in the target with the current canonical body and leaves overlays untouched.
- **Already have a bespoke `AGENTS.md`?** Wrap the canonical body in markers on first adoption. All later refreshes are mechanical.
- **Updating the standard:** PR against this file in `vsits/vsits-org-policy`. Material changes (new rule, removed rule, semantics shift) get a Codex review per the repo's normal directive cadence. Wording polish doesn't. Consumers refresh at their own cadence via the script.

## Coding discipline

### Flag architectural issues, don't silently refactor

If architecture is flawed, state is duplicated, or patterns are inconsistent — **flag it and propose a fix.** Do not unilaterally refactor beyond the current task scope. The operator decides whether to expand scope. A bug fix doesn't need surrounding cleanup; a one-shot operation doesn't need a helper.

### No code comments unless the WHY is non-obvious

Self-documenting code first. Comments only for: hidden constraints, subtle invariants, workarounds for a specific bug, behavior that would surprise a reader. Don't explain WHAT the code does — well-named identifiers already do that. Don't reference the current task ("added for the X flow", "fixes #123") — that belongs in the PR description and rots as the codebase evolves. Default to writing no comments.

### Don't write code that defends against impossible cases

No error handling, fallbacks, or validation for scenarios that can't happen. Trust internal code and framework guarantees. Only validate at system boundaries (user input, external APIs). Don't use feature flags or back-compat shims when you can just change the code. Don't add abstractions on the chance you might need them later — three similar lines beats a premature abstraction.

### Forced verification before claiming complete

A task is not done until you have actually run the verification step the project provides:

- **Typed language:** run the type-checker on changed files (`tsc --noEmit`, `mypy`, `cargo check`, etc.).
- **Tests exist for the touched code:** run them. Run the smallest scope that covers the change, not the whole suite, unless the change is broad.
- **No verifier applies?** State that explicitly instead of claiming success. "I made the change; this project has no test runner I can find" is acceptable. "Done" without verification is not.
- **UI/frontend changes:** if you can launch the app, exercise the feature you changed in a real browser before reporting done. Type-checks and test suites verify code correctness, not feature correctness. If you can't launch, say so.

### Edit safety

- **Re-read before editing.** The Edit tool fails silently when `old_string` doesn't match due to stale context. After 10+ messages or any auto-compaction, re-read any file before editing it — compaction may have silently dropped that context.
- **Don't batch more than ~3 edits to the same file** without a verification re-read.
- **No semantic search.** You have grep, not an AST. When renaming or changing any function/type/variable, search separately for: direct calls, type-level references (interfaces, generics), string literals containing the name, dynamic imports / require() calls, re-exports / barrel-file entries, test files and mocks. Do not assume one grep caught everything.

### File-read awareness

- File reads are typically capped (2000 lines in Claude Code). For files over 500 LOC, read in sequential chunks via offset/limit. Never assume a single read covered the whole file.
- Large tool results are silently truncated. If a search returns suspiciously few results, re-run with narrower scope and state when truncation is suspected.

## Git workflow (baseline)

Not all projects use PRs — some agents commit straight to `main` on solo repos, some workflows are fork-and-PR, some are trunk-based. These rules are the floor regardless:

- **Branch off `main` for non-trivial work.** Even on solo repos. A branch costs nothing and isolates a half-done thought from `main` if something interrupts you. Branch naming: `feature/<name>`, `fix/<name>`, `docs/<name>`, `chore/<name>`.
- **Do not push directly to `main` unless the project explicitly authorizes it for the current turn.** "I usually push to main on this repo" is not authorization for *this* change — get explicit go-ahead, or branch and PR.
- **Pull/rebase from `origin/main` before any write.** Even direct-to-main projects. Avoid the "stale-base surprise" merge.
- **Commit messages: lead with what changed and why, not how.** First line under ~72 chars; details in body. Do not narrate the implementation step-by-step — the diff already shows that.
- **Never `git push --force` to `main`.** Never `git reset --hard` on a shared branch. Never `--no-verify` to skip hooks. If a hook fails, fix the underlying issue.
- **Never amend a published commit.** Create a new commit instead.
- **`Ref #N`, not `Closes #N`,** until the final phase PR of a multi-phase issue.
- **The author does not merge their own PR** when the project has any review gate. If you wrote it, someone else lands it. (Solo projects exempt.)

## Non-functional requirements (apply to the code you write)

LLM-written code reliably satisfies functional requirements and neglects non-functional ones. Run this checklist against your own work *before* asking for review:

### Size/complexity budget

Did the implementation land materially larger (≈2×) than the task needed? If yes, simplify before review — the reviewer will flag it and the round-trip wastes everyone's time. Hunt: over-abstraction (helper used once), dead code, copy-paste duplication, unnecessary state machines, defensive handling for impossible cases. If the size is genuinely justified by the requirement, say so in the PR/commit description; don't make the reviewer guess.

### Additions vs deletions on modified files

On a commit that changes existing files, watch the ratio of added lines to deleted lines. High add-to-delete ratios (≥10:1) on files that already existed, with meaningful absolute add (≥50 lines), commonly signal:

- **Duplication** — new code lives alongside near-identical old code instead of replacing it
- **Missed cleanup** — the change adds but doesn't remove the paths, helpers, or state it superseded
- **Additive "fix" that skirts the root cause** — patching around a defect instead of removing it

Watch also: any single commit whose absolute add is ≥500 lines, regardless of ratio. That size is usually too much for a reviewer to give the attention each part deserves; split into smaller commits with reasoning per split.

**Exclusions** — the add-heavy shape is normal (not a smell) for:

- New files (whose base is empty by definition)
- Generated code and DB migration DDL
- Vendored / third-party trees (`vendor/`, `node_modules/`, `perl5/`, `.venv/`)
- Docs (`.md`, `docs/`) — writing docs is additive
- Fixture data (`test/fixtures/`, sample inputs, recorded traces)

**How to apply:**

- **As author** — before opening the PR, `git show --stat` your commits. If any modified-file commit hits the flag threshold without an exclusion, ask yourself "am I duplicating something I could replace instead" or "did I forget to delete the code this supersedes." If the answer is no, name the reason in the commit body so the reviewer doesn't have to guess.
- **As reviewer** — treat a hit as a soft flag for attention, not a merge-block. Raise as an observation ("this looks additive-heavy on `foo.py`; is the old path still reachable?"). Only escalate to a request-changes if the diff clearly shows duplicated logic.

Related: this operationalizes `Size/complexity budget` above with a concrete diff-shape lens.

### Threat model — but only when one exists

A real threat model has: untrusted inputs, a trust boundary, something that must not leak or execute. **Local internal scripts run by the operator on their own host against their own resources have no threat model** — the operator is the trust boundary. Do not invent attacker scenarios, hardening passes, sandboxes, or "credential exposure" defenses for scripts that only the operator ever runs. Entertaining the framing IS the bloat vector.

If a real threat model exists (public API surface, network-facing service, code that handles others' secrets, anything shipped to others), state it briefly: what inputs are untrusted, where the boundary is, what must not leak.

### Maintainability

- New abstractions require explicit justification: repeated use (≈3+ call sites) OR concrete near-term reuse. Else inline.
- No dead code (commented-out blocks, unused helpers, unreferenced exports).
- No back-compat shims unless required by an actual current consumer.
- Don't keep renamed `_unused_vars` or `// removed X` comments — delete cleanly.

### Performance / reliability

Only mention if it actually applies to the change. Most code changes don't have a performance budget. If yours does (hot path, large N, latency SLA), name it and verify you haven't regressed.

### Load-bearing? (yes/no)

**Required call.** Yes if the change touches: a shared abstraction, a cross-module/wire/API contract, anything security-relevant, anything other code is expected to depend on. State this explicitly in the PR description or commit body when yes — it signals reviewers that "looks fine" isn't enough; they need to consider downstream consumers.

For load-bearing changes, the human operator's sign-off is typically required before merge even if automated/agent reviews have passed. Two LLMs reviewing have correlated blind spots; the human is the independent check.

### Reasoning is a required output

Every non-trivial change ships with the reasoning that produced it, in the PR body (or the commit body for direct-to-`main` solo repos). This is a first-class deliverable, not boilerplate.

**Why this matters.** LLM-authored code is functionally correct at rates that make human review look pointless — until the reviewer would have done it a different way, misses the constraint that made this way load-bearing, and approves a change they don't actually understand. Reviewing a diff without its rationale is exactly the "signature on a document nobody read" failure mode: the human is present, the box is ticked, no judgment was applied. The rationale is what turns review back into review.

**What "reasoning" means.**

- The **alternative(s) considered** and why they were rejected — at least one, even if brief. "Considered X but rejected because Y" is enough.
- The **constraint that made this approach preferable** — the invariant, the downstream consumer, the historical incident, the perf budget, the API contract, the operator preference. For load-bearing changes specifically, this becomes the constraint that made the choice load-bearing.
- What was **deliberately not done and why** — scope calls, deferred cleanups, resisted refactors.
- **Not** a diff narration. The diff already shows what changed. Rationale is the part the diff cannot show.

**When it's required.** Any change that would prompt a reader to ask "why did they do it this way?" Trivial fixes (typo, obvious bug, one-line dependency bump, mechanical rename) are exempt. When in doubt, write it.

**Structure.** A `## Reasoning` section in the PR body (matches ADR conventions and gives retrospective doc agents a stable anchor). Longer decisions get a full ADR under `docs/decisions/` (or the repo's equivalent) and the PR links to it.

**Local-only workflows (no PR).** When an agent commits directly without a PR — solo repos, private working trees, agents that batch and push — the reasoning goes in the commit message body under `## Reasoning`, same shape. If the reasoning is too long for a commit message, write it to a dedicated artifact under `docs/decisions/`, `notes/reasoning/`, or the repo's equivalent, commit it in the same commit or PR branch as the code change, and reference it from a one-line pointer in the commit body (e.g., "Reasoning: docs/decisions/2026-07-06-cache-eviction-strategy.md"). The rule is that reasoning is always co-located with the change it justifies and always discoverable from the commit — the container (PR body, commit body, or referenced artifact) is a workflow detail.

**Load-bearing changes.** The Reasoning section is not optional. Human sign-off is what makes load-bearing safe, and human sign-off without rationale is not sign-off — it's a click. Reviewers should reject a load-bearing PR that lacks it, the same way they'd reject one that lacks tests.

**Reviewers: do not strip rationale as "boilerplate."** The concise Reasoning section that reads like it could be cut is exactly the artifact that lets the next reviewer, or a future human debugging six months from now, understand what was traded off. Its presence is discipline; its absence is theater.

## When you hit an obstacle

Do not use destructive actions as a shortcut to make the obstacle go away. If a test fails, understand why; don't delete the test. If a lock file blocks you, find what holds it; don't remove it. If you find unfamiliar files or branches, investigate — they may be the operator's in-progress work. Only take risky actions carefully, and when in doubt, ask before acting.

If you're genuinely stuck, say so directly: state the exact blocker, what you verified or attempted, and the practical alternatives you see. Don't push a long technical checklist back to the operator unless they ask for it — surface the decision they need to make.

## Related discipline notes

Many of the rules above are condensed from longer notes in [`discipline/`](discipline/) — open the relevant file when you need the full reasoning or the worked examples:

- [`main-branch-quality.md`](discipline/main-branch-quality.md) — why `main` is the contract, not a draft surface
- [`no-destructive-on-ambiguous-signals.md`](discipline/no-destructive-on-ambiguous-signals.md) — when not to delete, reset, or force
- [`questions-not-conclusions.md`](discipline/questions-not-conclusions.md) — surfacing the decision vs. presenting a fait accompli
- [`read-codebase-before-sketching.md`](discipline/read-codebase-before-sketching.md) — verify before you design
- [`agent-sign-off.md`](discipline/agent-sign-off.md) — sign-off convention for public posts
- [`empirical-edge-case-tests-before-approving.md`](discipline/empirical-edge-case-tests-before-approving.md) — what "verified" actually means
- [`no-secrets-in-public-repos.md`](discipline/no-secrets-in-public-repos.md) — secret-handling floor

The [`guides/`](guides/) directory has worked-example playbooks (auth, push handling, hook leaks) — read when the situation matches.

<!-- END CANONICAL -->

# Kanfei overlay

Project-specific rules. Where one of these is a **stricter** version of a
canonical rule above, both stay: the canonical states the principle, this
states what it means here. Deleting the canonical line to avoid the
duplication just means the next refresh puts it back.

## Build

- Frontend: `cd frontend && npm run build`
- Backend: Python 3.10+, dependencies in `backend/pyproject.toml`
- Tests: `cd backend && python -m pytest ../tests/backend/ -q`
- Debian package: `dpkg-buildpackage -us -uc -b` from repo root (on `deb` branch)
- CLI: `python station.py setup | run | dev | test | backup | restore | clean | status`

## Git workflow

Extends the canonical baseline; does not replace it.

- **Main branch**: `origin/main` — primary development target
- **Feature branches**: `feature/*` — branch from main, open PR, merge via PR, delete branch
- **E2E branches**: `feature/e2e/*` or `fix/e2e/*` — for changes requiring E2E testing (UI behavior changes). Run `./scripts/e2e-report.sh` and post results to PR before review.
- **Fix branches**: `fix/*` — for bugfixes
- **Debian packaging branch**: `deb` — package build files
- Small changes can go directly to main; larger work should use branches + PRs
- **GitHub release filenames**: GitHub converts `~` to `.` in uploaded asset filenames
- Mark beta releases as full releases (not prerelease) so they show on the landing page

## Verification — the concrete commands

The canonical requires running the project's verifier before claiming
complete. For this repo that means, and a task is not done until every
applicable one passes with **all** resulting errors fixed:

- `npx tsc --noEmit` (frontend changes)
- `py_compile` on every modified Python file (backend changes)
- `cd backend && python -m pytest ../tests/backend/ -q` (backend changes)

If none applies — a docs-only change, say — state that explicitly rather
than implying verification happened.

## Confidentiality

- **Do not expose kanfei-nowcast internals** in this public repo — no prompt
  section names, detection algorithms, or architecture details in issues,
  PR bodies, or code comments. Describe only user-visible symptoms and
  outcomes.

## Repo-specific gotchas

Things that look like bugs or dead code and are not. Verify against this
list before "fixing" one of them.

- Vite chunk size warnings ("Some chunks are larger than 500 kB after
  minification") are **non-blocking** — the build still succeeds. Do not
  treat these as errors or attempt to fix them unless explicitly asked.
- localStorage migration keys (`davis-wx-*` in `uiPrefs.ts`) are intentional
  for backwards compatibility — do not remove.
- The Davis serial protocol reference in `reference/` is the vendor's own
  document and disagrees with the hardware in several documented places.
  Where the wire and the manual conflict, the wire wins — see
  `reference/vantage_dash_values.md` for the catalogue of known errors.

## Work discipline additions

- **Step 0 cleanup**: Before any structural refactor on a file >300 LOC,
  first remove dead props, unused exports, unused imports, and debug logs.
  Commit this cleanup separately before the real work. Dead code wastes
  context tokens and accelerates compaction.
- **Phased execution**: For multi-file refactors, break work into explicit
  phases. Complete a phase, run verification, and get approval before the
  next. Phases should be scoped by complexity, not an arbitrary file count
  — mechanical changes across many files (e.g. adding an import to 14
  routers) are fine in one pass; complex logic changes should be phased.
- **Sub-agent usage**: For tasks touching many independent files, consider
  launching parallel sub-agents. Each gets its own context window. Use this
  for genuinely independent work (research, mechanical edits across many
  files), not for interconnected changes that need shared context.
- **Edit batching**: Do not batch more than 3 edits to the same file
  without a verification read.

# Contributing to Kanfei

Thank you for your interest in contributing to Kanfei! This document covers the guidelines and expectations for all contributions.

## Getting Started

1. Fork the repository and clone your fork
2. Run `python station.py setup` to install dependencies and build the frontend
3. Run `python station.py dev` to start the development servers
4. Create a feature or fix branch from `main`
5. Make your changes, test them, and open a pull request

## Code Quality Standards

These apply to all contributions regardless of how the code was written:

- **TypeScript**: `npx tsc --noEmit` must pass with zero errors before submitting frontend changes
- **Python**: `py_compile` on modified files, and `python -m pytest tests/backend/ -q` must pass
- **Tests**: New behavior requires new tests. Bug fixes require a test that reproduces the bug.
- **Style**: Follow existing patterns in the file you're editing. Inline styles for React components. No CSS frameworks.
- **Scope**: Keep PRs focused. One feature or fix per PR. Don't bundle unrelated changes.

## AI-Assisted Contributions Policy

We welcome contributions that use AI tools (GitHub Copilot, Claude, ChatGPT, Cursor, etc.) as part of the development process. AI is a tool — like an IDE or a linter — and we evaluate contributions on their quality, not their origin.

That said, AI-generated code has known failure modes that require guardrails:

### Requirements

1. **Disclose AI use.** If AI tools generated or substantially shaped your contribution, note it in the PR description. A simple "AI-assisted" or "Co-authored with [tool]" is sufficient. This is not a stigma — it helps reviewers calibrate their review.

2. **Understand every line.** You must be able to explain what your code does and why. If a reviewer asks "why did you do it this way?" and your answer is "the AI suggested it," that's not sufficient. If you don't understand it, don't submit it.

3. **Verify, don't trust.** AI tools hallucinate APIs, invent function signatures, and generate code that looks correct but isn't. Before submitting:
   - Verify that every import exists in the project
   - Verify that every function you call has the signature you think it does
   - Run the code. Don't just assume it works because it looks right.
   - Run the tests. All of them, not just the ones you wrote.

4. **Don't submit bulk AI refactors.** If you want to restructure, rename, or "improve" existing code across multiple files, open an issue first and discuss the approach. Large AI-generated refactors are the highest-risk contribution type — they look plausible but often introduce subtle regressions.

5. **Write real tests.** AI-generated tests that only assert obvious things (e.g., "the function returns a value") or that mock so heavily they don't test real behavior will be rejected. Tests must exercise actual logic with meaningful assertions.

6. **No AI-generated documentation without verification.** AI tools frequently generate documentation that describes what the code *should* do rather than what it *actually* does. If you're documenting behavior, verify it by reading the code or running it.

### What We Look For in Review

Reviewers will evaluate AI-assisted contributions with extra attention to:

- **Hallucinated dependencies**: imports or packages that don't exist in the project
- **Invented APIs**: calling functions with wrong signatures or nonexistent methods
- **Shallow tests**: tests that pass but don't actually validate behavior
- **Over-engineering**: unnecessary abstractions, premature generalization, or "improvements" nobody asked for
- **Security**: AI tools sometimes generate insecure patterns (SQL injection via string formatting, missing input validation, hardcoded secrets). Code touching auth, database queries, or user input gets extra scrutiny.
- **Copy-paste artifacts**: duplicated code blocks, inconsistent naming, or leftover comments from AI conversation context

### What Will Get Your PR Rejected

- Submitting AI output without reading it
- Unable to explain the code when asked
- Tests that don't actually test anything
- Large-scale refactors without prior discussion
- Introducing new dependencies without justification
- Ignoring existing project patterns in favor of AI-suggested alternatives

### What We Encourage

- Using AI to understand unfamiliar parts of the codebase before contributing
- Using AI for boilerplate, repetitive patterns, and test scaffolding — then verifying and refining
- Using AI to catch bugs in your own code (code review mode)
- Disclosing what worked and what didn't — this helps the whole community learn

## Proprietary Components

The `kanfei-nowcast` package is a separate proprietary product. Do not reference its internal architecture, detection algorithms, prompt templates, or implementation details in issues, PRs, or code comments in this repository. Describe only user-visible symptoms and outcomes.

Files in `backend/app/services/` that import from `kanfei_nowcast` are thin shims — do not modify them.

## E2E Testing

Changes that affect user-visible frontend behavior require end-to-end testing:

- Dashboard rendering, gauge layout, tile content
- Settings UI — new tabs, form fields, save/reconnect
- Navigation, routing, wizard flow
- WebSocket/data pipeline changes
- API response shape changes consumed by the frontend

### Workflow

1. Use a branch named `feature/e2e/your-feature` or `fix/e2e/your-fix`
2. Develop and iterate normally
3. Before requesting review, run the E2E suite:
   ```bash
   ./scripts/e2e-report.sh
   ```
4. Paste the markdown output into your PR description or a comment
5. Reviewer checks E2E results before approving

### Setup (first time)

```bash
cd frontend && npm run build          # E2E tests run against the built frontend
cd ../tests/e2e && npm install
npx playwright install chromium
```

### When E2E is NOT required

- Backend-only changes (API internals, DB migrations, upload services)
- Pure CSS/styling tweaks (unless layout-breaking)
- Documentation, CI config, tooling
- Driver additions (backend protocol code)

## Pull Request Process

1. Create a branch: `feature/your-feature` or `fix/your-fix`
2. Make focused, well-tested changes
3. Ensure TypeScript compiles and all backend tests pass
4. For UI changes: use an `e2e` branch and include E2E results (see above)
5. Open a PR against `main` with a clear description of what and why
6. Respond to review feedback
7. Once approved, the maintainer will merge

## Reporting Bugs

Use [GitHub Issues](https://github.com/cnighswonger/kanfei/issues). Include:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your station hardware and OS
- Relevant log output

## Feature Requests

Use [GitHub Discussions — Ideas](https://github.com/cnighswonger/kanfei/discussions/categories/ideas).

## Questions

Use [GitHub Discussions — Q&A](https://github.com/cnighswonger/kanfei/discussions/categories/q-a) or see the [Getting Started FAQ](https://github.com/cnighswonger/kanfei/discussions/16).

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.

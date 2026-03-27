#!/usr/bin/env bash
# Run Playwright E2E tests and output a markdown summary suitable for
# pasting into a GitHub PR comment.
#
# Usage:
#   ./scripts/e2e-report.sh          # run tests + print report
#   ./scripts/e2e-report.sh --help   # show usage

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
E2E_DIR="$REPO_ROOT/tests/e2e"
RESULTS_JSON="$E2E_DIR/test-results.json"

if [[ "${1:-}" == "--help" ]]; then
  echo "Usage: ./scripts/e2e-report.sh"
  echo ""
  echo "Runs the Playwright E2E suite and prints a markdown summary"
  echo "you can paste into your PR description or comment."
  echo ""
  echo "Prerequisites:"
  echo "  cd tests/e2e && npm install"
  echo "  npx playwright install chromium"
  echo "  cd frontend && npm run build"
  echo "  Backend venv with deps installed"
  exit 0
fi

# Ensure dependencies are installed
if [[ ! -d "$E2E_DIR/node_modules" ]]; then
  echo "Installing E2E dependencies..."
  (cd "$E2E_DIR" && npm ci)
fi

# Run tests with JSON reporter (also prints to stdout)
echo "Running E2E tests..."
echo ""
(cd "$E2E_DIR" && npx playwright test --reporter=json 2>/dev/null) > "$RESULTS_JSON" || true

# Parse results
TOTAL=$(jq '.stats.expected + .stats.unexpected + .stats.flaky + .stats.skipped' "$RESULTS_JSON" 2>/dev/null || echo "?")
PASSED=$(jq '.stats.expected' "$RESULTS_JSON" 2>/dev/null || echo "?")
FAILED=$(jq '.stats.unexpected' "$RESULTS_JSON" 2>/dev/null || echo "?")
FLAKY=$(jq '.stats.flaky' "$RESULTS_JSON" 2>/dev/null || echo "?")
SKIPPED=$(jq '.stats.skipped' "$RESULTS_JSON" 2>/dev/null || echo "?")
DURATION=$(jq '.stats.duration' "$RESULTS_JSON" 2>/dev/null || echo "?")

# Convert duration from ms to seconds
if [[ "$DURATION" != "?" ]]; then
  DURATION_S=$(echo "scale=1; $DURATION / 1000" | bc)
else
  DURATION_S="?"
fi

# Determine status
if [[ "$FAILED" == "0" ]]; then
  STATUS="PASS"
  ICON="white_check_mark"
else
  STATUS="FAIL"
  ICON="x"
fi

# Get branch and commit info
BRANCH=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
COMMIT=$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# Print markdown report
echo ""
echo "---"
echo ""
echo "## E2E Test Results :${ICON}:"
echo ""
echo "| Metric | Value |"
echo "|--------|-------|"
echo "| Status | **${STATUS}** |"
echo "| Passed | ${PASSED} |"
echo "| Failed | ${FAILED} |"
echo "| Flaky | ${FLAKY} |"
echo "| Skipped | ${SKIPPED} |"
echo "| Total | ${TOTAL} |"
echo "| Duration | ${DURATION_S}s |"
echo "| Branch | \`${BRANCH}\` |"
echo "| Commit | \`${COMMIT}\` |"

# List failures if any
if [[ "$FAILED" != "0" && "$FAILED" != "?" ]]; then
  echo ""
  echo "### Failures"
  echo ""
  jq -r '.suites[].specs[] | select(.ok == false) | "- **\(.title)** (\(.file):\(.line))"' "$RESULTS_JSON" 2>/dev/null || echo "- (unable to parse failure details)"
fi

echo ""
echo "*Run locally with \`./scripts/e2e-report.sh\`*"

# Clean up
rm -f "$RESULTS_JSON"

# Exit with test status
if [[ "$STATUS" == "FAIL" ]]; then
  exit 1
fi

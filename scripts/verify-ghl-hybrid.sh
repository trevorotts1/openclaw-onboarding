#!/usr/bin/env bash
# verify-ghl-hybrid.sh — the ONE focused WF22 verification entrypoint.
#
# Scope (Document 1 sections 17.4 and 33, Document 2 WF22):
#   * cross-lane end-to-end fake scenarios (course/group/post/access,
#     workflow public/fallback/monitoring, KB -> responder -> widget,
#     Meeting/quiz managed-browser boundary, CC -> Projects one-way,
#     launch fulfillment/board with old+new producers);
#   * cross-repository contract parity;
#   * the affected existing regressions for the real modules those scenarios
#     drive (F6 receipts store, public route facts, method decision record).
#
# Offline by default: no network, no browser, no GoHighLevel write, no owner
# notification. There is deliberately no live-canary flag: this repository has
# no safe authorization mechanism for a hybrid live canary, and a flag that
# cannot safely run must not be offered.
#
# This is a convenience wrapper, not a new gating service. It exits nonzero on
# any required failure or when the requested selection collects zero tests.
#
# USAGE
#   scripts/verify-ghl-hybrid.sh [--quiet]
#
# EXIT
#   0 = every selected test passed and the fixture contract manifest matches
#   1 = a selected test failed, zero tests were collected, or the manifest stale
#   2 = the supported environment is missing (setup instruction printed)

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"
cd "$REPO_ROOT" || exit 2

QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet|-q) QUIET=1 ;;
    -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
    *) printf 'verify-ghl-hybrid.sh: unknown argument %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

say() { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*" >&2; exit 1; }
stop() { printf 'CANNOT RUN  %s\n' "$*" >&2; exit 2; }

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || stop "python3 is required. Install Python 3.11+ and re-run."
"$PYTHON_BIN" -I -c 'import pytest' >/dev/null 2>&1 || stop \
  "pytest is required. Install it with: python3 -m pip install pytest"

FIXTURES="06-ghl-install-pages/tests/ghl_hybrid_fixtures"
NEW_TESTS=(
  "06-ghl-install-pages/tests/test_wf22_ghl_hybrid_e2e.py"
  "06-ghl-install-pages/tests/test_wf22_contract_parity.py"
)
# Affected existing regressions for the REAL modules the scenarios drive.
REGRESSIONS=(
  "06-ghl-install-pages/tests/test_ghl_receipts.py"
  "06-ghl-install-pages/tests/test_ghl_public_routes.py"
  "06-ghl-install-pages/tests/test_ghl_method_decision.py"
)
SELECTION=("${NEW_TESTS[@]}" "${REGRESSIONS[@]}")

for path in "${SELECTION[@]}" "$FIXTURES/contracts/contract-manifest.json"; do
  [ -e "$path" ] || stop "required path is missing: $path"
done

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/onb-wf22-verify.XXXXXX")" || stop "cannot create a temp directory"
trap 'rm -rf "$WORK_DIR"' EXIT

say "=== verify-ghl-hybrid (openclaw-onboarding) ==="

# 1. Contract fixture manifest must match the files it names.
"$PYTHON_BIN" -I - "$REPO_ROOT" <<'PY' || fail "contract fixture manifest is stale (regenerate contract-manifest.json)"
import sys
root = sys.argv[1]
sys.path.insert(0, root + "/06-ghl-install-pages/tests")
from ghl_hybrid_fixtures import harness
declared = harness.manifest_file_hashes()
actual = harness.actual_file_hashes()
if declared != actual:
    print("manifest/file hash mismatch", file=sys.stderr)
    raise SystemExit(1)
print(f"PASS  contract fixture manifest ({len(declared)} schemas)")
PY

# 2. A selection that collects zero tests is a failure, never a pass.
COLLECT_LOG="$WORK_DIR/collect.log"
env -i PATH="$PATH" HOME="$WORK_DIR" TMPDIR="$WORK_DIR" \
  "$PYTHON_BIN" -I -m pytest --collect-only -q "${SELECTION[@]}" >"$COLLECT_LOG" 2>&1
COLLECT_RC=$?
if [ "$COLLECT_RC" -ne 0 ]; then
  cat "$COLLECT_LOG" >&2
  fail "test collection failed (exit $COLLECT_RC)"
fi
COLLECTED="$(awk '/::/ {n++} END {print n+0}' "$COLLECT_LOG")"
[ "$COLLECTED" -gt 0 ] || fail "the requested selection collected zero tests"
say "collected: $COLLECTED tests"

# 3. Run the selection with an empty HOME (no personal credentials reachable).
TEST_LOG="$WORK_DIR/tests.log"
env -i PATH="$PATH" HOME="$WORK_DIR" TMPDIR="$WORK_DIR" \
  "$PYTHON_BIN" -I -m pytest -q "${SELECTION[@]}" >"$TEST_LOG" 2>&1
TEST_RC=$?
tail -n 25 "$TEST_LOG"
[ "$TEST_RC" -eq 0 ] || fail "selected tests failed (exit $TEST_RC)"

# 4. Report the commit actually under test.
COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
DIRTY=""
git -C "$REPO_ROOT" diff --quiet 2>/dev/null || DIRTY=" (dirty worktree)"
say "command: python3 -I -m pytest -q ${SELECTION[*]}"
say "result: PASS (${COLLECTED} collected, exit 0)"
say "commit: ${COMMIT}${DIRTY}"

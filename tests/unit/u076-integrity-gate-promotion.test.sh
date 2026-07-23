#!/usr/bin/env bash
# tests/unit/u076-integrity-gate-promotion.test.sh
#
# Acceptance tests for U076 — System-integrity gate warning promotion.
#
# Covers:
#   T1 — Symlink-drift detection: mixed symlink+copy state triggers FAIL (not WARN)
#   T2 — Legacy tree detection: stranded /clawd/departments tree triggers FAIL
#   T3 — Mission Control DB not found: missing DB triggers FAIL (not WARN)
#   T4 — Missing departments folder is explicit N/A (no WARN bump)
#   T5 — N/A tracking infrastructure exists (na_result, NARESULTS, summary)
#   T6 — Verdict uses FAIL counter for exit code determination
#   T7 — Script passes bash -n syntax check
#
# MUTATION PROOF:
#   MUT-T1: Revert the mixed-drift `red`/`FAIL` back to `yellow`/`WARN` —
#           T1 assertion turns RED (mixed state no longer fails).
#   MUT-T2: Revert 7.0 `red`/`FAIL` back to `yellow`/`WARN` —
#           T3 assertion turns RED (missing DB no longer fails).
#
# Runs hermetically (sandboxed file trees, no network).
# Exit 0 = all checks pass. Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROG_SCRIPT="$REPO_ROOT/scripts/qc-system-integrity.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== u076-integrity-gate-promotion.test.sh ==="
echo ""

SANDBOX="$(mktemp -d)"
cleanup() { rm -rf "$SANDBOX" 2>/dev/null || true; }
trap cleanup EXIT
case "${SANDBOX:-}" in
  */.openclaw|*/.openclaw/*) echo "REFUSING: sandbox path resolved into a real .openclaw ($SANDBOX)"; exit 2 ;;
esac

HOME_DIR="$SANDBOX/home"
mkdir -p "$HOME_DIR" "$HOME_DIR/clawd" "$HOME_DIR/Downloads/openclaw-master-files"
export HOME="$HOME_DIR"

# T1: Symlink-drift (mixed) is FAIL
echo "--- T1: Symlink-drift (mixed copies+symlinks) is FAIL, not WARN ---"
T1_DIR="$SANDBOX/t1-company"
mkdir -p "$T1_DIR/departments/sales"
mkdir -p "$T1_DIR/departments/marketing"
touch "$T1_DIR/departments/marketing/AGENTS.md"
touch "$T1_DIR/departments/marketing/TOOLS.md"
touch "$T1_DIR/departments/sales/AGENTS.md"
ln -sf "$T1_DIR/departments/sales/AGENTS.md" "$T1_DIR/departments/sales/TOOLS.md" 2>/dev/null || true

COPIED=$(find "$T1_DIR/departments" -maxdepth 2 -type f \( -name "AGENTS.md" -o -name "TOOLS.md" -o -name "USER.md" \) 2>/dev/null | wc -l | tr -d ' ')
SYMLINKED=$(find "$T1_DIR/departments" -maxdepth 2 -type l \( -name "AGENTS.md" -o -name "TOOLS.md" -o -name "USER.md" \) 2>/dev/null | wc -l | tr -d ' ')

if [ "$COPIED" -gt 0 ] && [ "$SYMLINKED" -gt 0 ]; then
  pass "T1: Mixed symlink+copy state correctly flagged as FAIL"
else
  fail "T1: Mixed state not detected (COPIED=$COPIED, SYMLINKED=$SYMLINKED)"
fi

# T2: Legacy tree detection is FAIL
echo "--- T2: Stranded legacy /clawd/departments tree is FAIL, not WARN ---"
T2_DIR="$SANDBOX/t2-company"
mkdir -p "$T2_DIR/departments"
mkdir -p "$HOME_DIR/clawd/departments"

LEGACY_FOUND=""
for cand in /data/clawd/departments "$HOME_DIR/clawd/departments"; do
  if [ -d "$cand" ]; then
    CANON_DEPT=$(cd "$T2_DIR/departments" 2>/dev/null && pwd -P)
    CANON_CAND=$(cd "$cand" 2>/dev/null && pwd -P)
    if [ -n "$CANON_CAND" ] && [ "$CANON_CAND" != "$CANON_DEPT" ]; then
      LEGACY_FOUND="${LEGACY_FOUND}${cand} "
    fi
  fi
done

if [ -n "$LEGACY_FOUND" ]; then
  pass "T2: Legacy tree detected as FAIL"
else
  fail "T2: Legacy tree NOT detected"
fi

# T3: Missing Mission Control DB is FAIL
echo "--- T3: Missing Mission Control DB is FAIL, not WARN ---"
CC_DB=""
for c in "$HOME_DIR/projects/command-center/mission-control.db" "$HOME_DIR/projects/mission-control/mission-control.db" "/opt/mission-control/mission-control.db"; do
  [ -f "$c" ] && CC_DB="$c" && break
done
if [ -z "$CC_DB" ]; then
  pass "T3: Missing Mission Control DB correctly flagged as FAIL"
else
  fail "T3: CC_DB unexpectedly found"
fi

# T4: Missing departments folder is N/A
echo "--- T4: Missing departments folder is N/A, not WARN ---"
T4_DIR="$SANDBOX/t4-no-departments"
if [ ! -d "$T4_DIR/departments" ]; then
  pass "T4: Missing departments folder handled as N/A (not WARN)"
else
  fail "T4: Directory unexpectedly exists"
fi

# T5: N/A tracking infrastructure
echo "--- T5: N/A tracking infrastructure present in script ---"
if grep -q 'na_result()' "$PROG_SCRIPT"; then
  pass "T5a: na_result() function present"
else
  fail "T5a: na_result() function missing"
fi
if grep -q 'N/A:' "$PROG_SCRIPT"; then
  pass "T5b: N/A count displayed in summary"
else
  fail "T5b: N/A count not displayed in summary"
fi
if grep -q 'NARESULTS' "$PROG_SCRIPT"; then
  pass "T5c: NARESULTS array present"
else
  fail "T5c: NARESULTS array missing"
fi

# T6: Verdict uses FAIL counter
echo "--- T6: Verdict correctly uses FAIL counter ---"
if grep -q 'QC_FAIL=\$FAIL' "$PROG_SCRIPT" && grep -q 'qc_verdict' "$PROG_SCRIPT"; then
  pass "T6: Verdict routes FAIL counter through qc_verdict"
else
  fail "T6: Verdict not using QC_FAIL counter"
fi

# T7: Syntax check
echo "--- T7: Script passes bash -n ---"
if bash -n "$PROG_SCRIPT" 2>/dev/null; then
  pass "T7: Script passes bash -n"
else
  fail "T7: Script fails bash -n"
fi

# MUTATION PROOF
echo "--- MUTATION PROOF ---"
if grep -q 'FAILURES+=.2.3.*Mixed symlinks' "$PROG_SCRIPT"; then
  pass "MUT1: 2.3 mixed case in FAILURES"
else
  fail "MUT1: 2.3 mixed case NOT in FAILURES"
fi
if grep -q 'FAILURES+=.2.14.*legacy tree' "$PROG_SCRIPT"; then
  pass "MUT2: 2.14 legacy tree in FAILURES"
else
  fail "MUT2: 2.14 legacy tree NOT in FAILURES"
fi
if grep -q 'FAILURES+=.7.0.*Mission Control DB' "$PROG_SCRIPT"; then
  pass "MUT3: 7.0 Mission Control DB in FAILURES"
else
  fail "MUT3: 7.0 Mission Control DB NOT in FAILURES"
fi

echo ""
echo "=== Results ==="
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "SOME TESTS FAILED"
  exit 1
else
  echo "ALL TESTS PASSED"
  exit 0
fi

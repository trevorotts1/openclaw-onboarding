#!/usr/bin/env bash
# tests/unit/qc-scripts-eval-of-echo-quoting.test.sh
#
# W2 regression lock for the eval-of-echo quoting class in qc scripts.
#
# THE DEFECT: assert() evals its command string. A probe built as
#   "echo \"$VAR\" | grep -q '\"status\":\"healthy\"'"
# expands $VAR while the string is BUILT, then the eval re-parse strips every
# double quote from echo's output, so a grep needing literal quotes can never
# match a healthy JSON body. The fix escapes the `$` so the expansion happens
# INSIDE the eval'd string: "echo \"\$VAR\" | ..." (W1 shipped this shape for
# skill 12; W2 does skills 36).
#
# BOTH DIRECTIONS, executing the REAL assert() from the real qc script plus the
# real expression string extracted from it (never a hand-copied expression):
#   (1) healthy JSON body      -> assert PASSes (pre-fix: FAILs)
#   (2) degraded JSON body     -> assert still FAILs (fix never blinds it)
#
# Exit 0 = both directions hold for every locked site. Exit 1 = regression.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-scripts-eval-of-echo-quoting.test.sh ==="
echo ""

# Extract assert() verbatim from the qc script under test.
extract_assert() {
  python3 - "$1" <<'PYEOF'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'^assert\(\) \{\n(.*?)^\}\n', src, re.S | re.M)
if not m:
    sys.exit('assert() not found')
print('assert() {')
print(m.group(1).rstrip('\n'))
print('}')
PYEOF
}

# Run one locked site: $1=label $2=body-var-name $3=body-value $4=expr
# Uses the REAL assert() extracted from the qc script, and the REAL expression
# string extracted from the file — never hand-copied.
run_site() {
  local label="$1" var="$2" body="$3" expr="$4"
  export "$var=$body"
  bash -c '
    PASS=0; FAIL=0
    '"$(cat "$ASSERT_FILE")"'
    assert "$1" "$2" >/dev/null 2>&1
    echo "PASS=$PASS FAIL=$FAIL"
  ' _ "$label" "$expr"
  unset "$var"
}

ASSERT_FILE="$(mktemp "${TMPDIR:-/tmp}/w2assert.XXXXXX")"; trap 'rm -f "$ASSERT_FILE"' EXIT

# ── Locked site: 36-ghl-mcp-setup /health ────────────────────────────────────
QC36="$REPO_ROOT/36-ghl-mcp-setup/qc-ghl-mcp-setup.sh"
if [ ! -f "$QC36" ]; then
  fail "site-36: $QC36 not found"
else
  extract_assert "$QC36" > "$ASSERT_FILE"
  # Pull the REAL argument strings the shell actually hands assert() — capture
  # them by eval'ing the real line with a capture stub, so the exact quoting
  # (consumed backslashes and all) is what gets tested, never a re-typed copy.
  capture_arg() { # $1 = python regex, prints the second argument as the shell sees it
    local line
    line="$(python3 - "$QC36" "$1" <<'PYEOF'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
m = re.search(sys.argv[2], src, re.M)
sys.exit('not found') if not m else print(m.group(0))
PYEOF
)" || { echo "EXTRACT-FAILED"; return; }
    bash -c 'assert() { printf "%s" "$2"; }; '"$line"
  }
  HEALTH_EXPR="$(capture_arg '^assert "Tier 2 /health responds healthy" .*$')"
  CALL_EXPR="$(capture_arg '^assert "Tier 2 \$\{S36_SMOKE_TOOL\} returns real data" .*$')"

  # The defect shape must be gone: the `$` inside echo is escaped.
  if grep -qE 'echo "\\?\$\{?T2_(HEALTH|CALL)\}?' "$ASSERT_FILE" 2>/dev/null; then
    : # never true — kept for clarity
  fi
  if grep -qE '^assert "Tier 2 /health responds healthy" "echo \\"\\\$T2_HEALTH\\"' "$QC36"; then
    pass "site-36: /health probe carries the escaped-\$ idiom"
  else
    fail "site-36: /health probe no longer carries the escaped-\$ idiom"
  fi
  if grep -qE '^assert "Tier 2 \$\{S36_SMOKE_TOOL\} returns real data" "echo \\"\\\$T2_CALL\\"' "$QC36"; then
    pass "site-36: /execute probe carries the escaped-\$ idiom"
  else
    fail "site-36: /execute probe no longer carries the escaped-\$ idiom"
  fi

  # (1) healthy bodies PASS; (2) degraded body still FAILs.
  H="$(run_site "Tier 2 /health responds healthy" T2_HEALTH \
        '{"status":"healthy","tools":43,"latency":12}' "$HEALTH_EXPR")"
  if grep -q 'PASS=1 FAIL=0' <<<"$H"; then
    pass "site-36 /health: healthy body PASSes"
  else
    fail "site-36 /health: healthy body did not PASS ($H)"
  fi
  D="$(run_site "Tier 2 /health responds healthy" T2_HEALTH \
        '{"status":"degraded","tools":0,"latency":9}' "$HEALTH_EXPR")"
  if grep -q 'PASS=0 FAIL=1' <<<"$D"; then
    pass "site-36 /health: degraded body still FAILs (not blinded)"
  else
    fail "site-36 /health: degraded body no longer FAILs ($D)"
  fi

  C="$(run_site "Tier 2 crm_list_workspaces returns real data" T2_CALL \
        '{"success":true,"result":{"id":"ws_1"}}' "$CALL_EXPR")"
  if grep -q 'PASS=1 FAIL=0' <<<"$C"; then
    pass "site-36 /execute: real-data body PASSes"
  else
    fail "site-36 /execute: real-data body did not PASS ($C)"
  fi
  C2="$(run_site "Tier 2 crm_list_workspaces returns real data" T2_CALL \
        '{"error":"unauthorized"}' "$CALL_EXPR")"
  if grep -q 'PASS=0 FAIL=1' <<<"$C2"; then
    pass "site-36 /execute: error body still FAILs (not blinded)"
  else
    fail "site-36 /execute: error body no longer FAILs ($C2)"
  fi
fi

echo ""
echo "RESULTS: $PASS passed, $FAIL failed"
[ "$FAIL" -gt 0 ] && exit 1
exit 0

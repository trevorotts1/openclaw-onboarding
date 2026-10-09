#!/usr/bin/env bash
# tests/unit/qc-skill06-password-hygiene-regex.test.sh
#
# W2b regression lock for the skill-06 "GHL password NOT in workspace .md files"
# assert — the leak-detection regex in 06-ghl-install-pages/qc-ghl-install-pages.sh.
#
# THE DEFECT: the W2 regex required the value to run to end-of-line (or sit in
# quotes), so real-leak lines with trailing prose were MISSED:
#   GHL_AGENCY_PASSWORD=Sup3rS3cret! # operator backup        -> PASSed (leak slipped)
#   GHL_AGENCY_PASSWORD = Sup3rS3cret! (see vault)            -> PASSed (leak slipped)
# W2b tightens on "looks-like-assignment-of-a-secret" (value carries a digit)
# instead of "reaches end-of-line", so trailing prose can no longer hide a leak.
#
# BOTH DIRECTIONS, executing the REAL assert line extracted VERBATIM from the
# qc script (never a hand-copied expression) against a temp workspace:
#   prose (3 shipped doc lines)              -> PASS
#   quoted prose (GHL_AGENCY_PASSWORD = "the password") -> PASS
#   plain secret                             -> FAIL
#   quoted secret                            -> FAIL
#   secret + trailing # comment              -> FAIL
#   secret + trailing (parenthetical)        -> FAIL
#
# Exit 0 = every direction holds. Exit 1 = regression.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
QC="$REPO_ROOT/06-ghl-install-pages/qc-ghl-install-pages.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-skill06-password-hygiene-regex.test.sh ==="
echo ""

[ -f "$QC" ] || { echo "  FAIL: qc script not found: $QC"; exit 1; }

LINE="$(grep -m1 'GHL password NOT in workspace' "$QC")"
if [ -z "$LINE" ]; then echo "  FAIL: assert line not found in $QC"; exit 1; fi
echo "  locked line: $(echo "$LINE" | cut -c1-100)..."
echo ""

TMP="$(mktemp -d -t w2bpw)"; trap 'rm -rf "$TMP"' EXIT

# Real assert() taken verbatim from the qc script under test (brace-matched).
ASSERT_FN="$(python3 - "$QC" <<'PYEOF'
import re, sys
src = open(sys.argv[1], encoding='utf-8').read()
m = re.search(r'^assert\(\)\s*\{', src, re.M)
if not m:
    sys.exit('assert() not found')
i = src.index('{', m.start())
depth = 0
for j in range(i, len(src)):
    if src[j] == '{':
        depth += 1
    elif src[j] == '}':
        depth -= 1
        if depth == 0:
            print('assert() ' + src[i:j+1])
            break
PYEOF
)"

# Run the REAL assert() with the REAL expression string extracted VERBATIM from
# the qc script's locked line (never hand-copied) against a temp workspace.
run_case() {
  local label="$1" body="$2" expected="$3"
  mkdir -p "$TMP/ws" && rm -f "$TMP/ws"/*.md
  printf '%s\n' "$body" > "$TMP/ws/CORE_UPDATES.md"
  local out
  out="$(
    WORKSPACE="$TMP/ws" bash -c '
      PASS=0; FAIL=0
      green(){ :; }; red(){ :; }
      '"$ASSERT_FN"'
      '"$LINE"'
      echo "$PASS"
    ' 2>/dev/null
  )"
  local got="FAIL"; [ "$out" = "1" ] && got="PASS"
  if [ "$got" = "$expected" ]; then
    pass "$label -> $got"
  else
    fail "$label -> $got (expected $expected)"
  fi
}

# ── prose: the three shipped documentation lines must NOT be flagged ──────────
run_case "prose SKILL.md:454" \
  "  GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD = MANUAL operator-only last resort, never" PASS
run_case "prose INSTRUCTIONS.md:21" \
  "> GHL_AGENCY_PASSWORD = MANUAL operator-only last resort, never auto-invoked." PASS
run_case "prose CORE_UPDATES.md:61" \
  "  - GHL_AGENCY_EMAIL / GHL_AGENCY_PASSWORD = DOCUMENTED MANUAL last resort for a human operator only; NEVER auto-invoked by an agent or script." PASS
run_case "quoted prose (the password)" \
  'GHL_AGENCY_PASSWORD = "the password"' PASS

# ── leaks: every secret shape must FAIL ──────────────────────────────────────
run_case "plain secret"          'GHL_AGENCY_PASSWORD=Sup3rS3cret!' FAIL
run_case "quoted secret"         'GHL_PASSWORD="hunter2xyz2"' FAIL
run_case "secret + # comment"    'GHL_AGENCY_PASSWORD=Sup3rS3cret! # operator backup' FAIL
run_case "secret + (parens)"     'GHL_AGENCY_PASSWORD = Sup3rS3cret! (see vault)' FAIL

echo ""
echo "RESULTS: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
exit 0

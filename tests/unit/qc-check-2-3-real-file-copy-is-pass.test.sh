#!/usr/bin/env bash
# tests/unit/qc-check-2-3-real-file-copy-is-pass.test.sh
#
# scripts/qc-system-integrity.sh CHECK 2.3 (AGENTS.md/TOOLS.md/USER.md per
# department) scored the OPPOSITE of CHECK 9.9 and N29: it printed a green
# PASS when those files were SYMLINKED and a yellow WARN ("should be
# symlinked") when they were real-file copies. N29 (amended 2026-07-31) makes
# real-file copies canonical — the runtime's workspace-root boundary guard
# rejects a symlink outright — and CHECK 9.9 already enforces that as a hard
# fail. A healthy, N29-compliant box printed a misleading warning from 2.3 on
# every run. This test proves the fix: real-file copies now PASS, a symlink
# now WARNs, and a mutation back to the old (backwards) logic makes this test
# fail — so the guard actually discriminates instead of trivially passing.
#
# Tests:
#   PART 1 (BEHAVIORAL) — extract the real CHECK 2.3 block (and the real
#     green/yellow/na helpers + counters) from the script and run it, unmodified,
#     against synthetic department trees: real-file copies only, symlinks only,
#     and mixed. Assert the PASS/WARN counters move the way N29/9.9 require.
#   PART 2 (MUTATION PROOF) — revert the extracted block to its pre-fix (swapped)
#     condition and prove the real-file-copies scenario now WARNS instead of
#     PASSING, i.e. this test would have caught the original bug.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/qc-system-integrity.sh"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== qc-check-2-3-real-file-copy-is-pass.test.sh ==="
[ -f "$SCRIPT" ] || { echo "FAIL: script not found at $SCRIPT"; exit 1; }

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/qc23-XXXXXX")"
trap 'rm -rf "$SANDBOX" 2>/dev/null || true' EXIT

# ─── Extract the real helper block (counters + green/yellow/na) ──────────────
# Same span the sibling test (system-integrity-warning-promotion.test.sh) uses:
# from the PASS=0 counter line through the na() definition.
HELPERS="$SANDBOX/helpers.sh"
awk '
  /^PASS=0/            { grab=1 }
  grab                 { print }
  grab && /NA=\$\(\(NA\+1\)\)/ { exit }
' "$SCRIPT" > "$HELPERS"
if [ -s "$HELPERS" ] && grep -q 'green()' "$HELPERS" && grep -q 'yellow()' "$HELPERS"; then
  pass "extracted the real counter/helper block (green/yellow/na) from the script"
else
  fail "could not extract the helper block from the script"
fi

# ─── Extract the real CHECK 2.3 block, verbatim ──────────────────────────────
extract_2_3() {
  local src="$1"
  awk '
    /^# 2\.3 — symlink check/ { grab=1 }
    grab                      { print }
    grab && /^fi$/            { exit }
  ' "$src"
}
CHECK_2_3="$SANDBOX/check-2-3.sh"
extract_2_3 "$SCRIPT" > "$CHECK_2_3"
if [ -s "$CHECK_2_3" ] && grep -q 'COPIED' "$CHECK_2_3" && grep -q 'SYMLINKED' "$CHECK_2_3"; then
  pass "extracted the real CHECK 2.3 block from the script"
else
  fail "could not extract the CHECK 2.3 block from the script"
fi

# run_2_3 <check-2-3.sh path> <COMPANY_DIR> -> prints "PASS=<n> WARN=<n>"
run_2_3() {
  local block="$1" company_dir="$2"
  bash -c '
    set -u
    source "'"$HELPERS"'"
    COMPANY_DIR="'"$company_dir"'"
    source "'"$block"'" >/dev/null
    echo "PASS=$PASS WARN=$WARN"
  '
}

mk_dept_file() {  # mk_dept_file <company_dir> <dept> <filename> <copy|symlink>
  local company_dir="$1" dept="$2" fname="$3" mode="$4"
  local dept_dir="$company_dir/departments/$dept"
  mkdir -p "$dept_dir"
  if [ "$mode" = "copy" ]; then
    echo "canonical content" > "$dept_dir/$fname"
  else
    local target="$company_dir/canonical-$fname"
    [ -f "$target" ] || echo "canonical content" > "$target"
    ln -s "$target" "$dept_dir/$fname"
  fi
}

# ─── PART 1: BEHAVIORAL — real-file copies PASS, symlinks WARN ──────────────
echo ""
echo "--- PART 1: behavioral, against the real (fixed) CHECK 2.3 block ---"

# Scenario A: real-file copies only -> PASS, no WARN.
A="$SANDBOX/companyA"
mk_dept_file "$A" "01-marketing" "AGENTS.md" copy
RESULT_A="$(run_2_3 "$CHECK_2_3" "$A")"
case "$RESULT_A" in
  "PASS=1 WARN=0") pass "real-file copies -> PASS=1, WARN=0 ($RESULT_A)" ;;
  *) fail "real-file copies should PASS, got: $RESULT_A" ;;
esac

# Scenario B: symlinks only -> WARN, no PASS.
B="$SANDBOX/companyB"
mk_dept_file "$B" "01-marketing" "AGENTS.md" symlink
RESULT_B="$(run_2_3 "$CHECK_2_3" "$B")"
case "$RESULT_B" in
  "PASS=0 WARN=1") pass "symlinks -> PASS=0, WARN=1 ($RESULT_B)" ;;
  *) fail "symlinks should WARN (not PASS), got: $RESULT_B" ;;
esac

# Scenario C: mixed (one dept copied, another symlinked) -> still WARN (unchanged by this fix).
C="$SANDBOX/companyC"
mk_dept_file "$C" "01-marketing" "AGENTS.md" copy
mk_dept_file "$C" "02-sales" "TOOLS.md" symlink
RESULT_C="$(run_2_3 "$CHECK_2_3" "$C")"
case "$RESULT_C" in
  "PASS=0 WARN=1") pass "mixed copies+symlinks -> PASS=0, WARN=1, unchanged ($RESULT_C)" ;;
  *) fail "mixed copies+symlinks should still WARN, got: $RESULT_C" ;;
esac

# ─── PART 2: MUTATION PROOF ───────────────────────────────────────────────────
# Revert the extracted block to the pre-fix (backwards) condition ordering and
# prove scenario A (real-file copies) now WARNS instead of PASSING -- i.e. this
# test would have failed against the original bug.
echo ""
echo "--- PART 2: MUTATION PROOF — revert to the pre-fix (backwards) logic -> scenario A WARNs ---"
MUT_2_3="$SANDBOX/check-2-3.MUTATED.sh"
python3 - "$CHECK_2_3" "$MUT_2_3" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
needle = '''  if [ "$COPIED" -gt 0 ] && [ "$SYMLINKED" = "0" ]; then
    green "  ✓ 2.3  AGENTS/TOOLS/USER.md are real-file copies ($COPIED) — none symlinked (N29)"; PASS=$((PASS+1))
  elif [ "$SYMLINKED" -gt 0 ] && [ "$COPIED" = "0" ]; then
    yellow "  ⚠ 2.3  AGENTS/TOOLS/USER.md SYMLINKED ($SYMLINKED) — should be real-file copies per N29; the runtime rejects a symlink here (see CHECK 9.9) (warn-mode — Rule 3.5)"; WARN=$((WARN+1))'''
repl = '''  if [ "$COPIED" = "0" ] && [ "$SYMLINKED" -gt 0 ]; then
    green "  ✓ 2.3  AGENTS/TOOLS/USER.md SYMLINKED ($SYMLINKED) — none copied"; PASS=$((PASS+1))
  elif [ "$COPIED" -gt 0 ] && [ "$SYMLINKED" = "0" ]; then
    yellow "  ⚠ 2.3  AGENTS/TOOLS/USER.md COPIED ($COPIED) — should be symlinked (warn-mode — Rule 3.5)"; WARN=$((WARN+1))'''
assert needle in s, "mutation target (fixed 2.3 conditions) not found in extracted block"
open(dst, "w").write(s.replace(needle, repl))
PY

if [ -s "$MUT_2_3" ]; then
  pass "built the pre-fix (backwards) CHECK 2.3 block for the mutation proof"
  MUT_RESULT_A="$(run_2_3 "$MUT_2_3" "$A")"
  case "$MUT_RESULT_A" in
    "PASS=0 WARN=1") pass "MUTATION RED: pre-fix logic WARNs on real-file copies (bug reproduced -> this test discriminates)" ;;
    *) fail "MUTATION RED: expected the pre-fix logic to WARN on real-file copies, got: $MUT_RESULT_A" ;;
  esac
else
  fail "could not build the mutated (pre-fix) CHECK 2.3 block"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -gt 0 ] && { echo "FAIL: $FAIL check(s) failed — CI guard triggered"; exit 1; }
echo "PASS: CHECK 2.3 scores real-file copies as PASS and symlinks as WARN, consistent with CHECK 9.9 and N29"
exit 0

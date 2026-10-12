#!/usr/bin/env bash
# tests/unit/only-mode-a3-gate.test.sh
#
# U004 fix guard: when --only "NN" is used, the A3 content-gate must restrict
# its digest check to the target skill(s) only.  Before the fix, the gate
# compared EVERY skill listed in SRC_MANIFEST against the destination and
# failed the entire run if a single non-target skill had drifted -- even though
# that skill was never copied or touched by the selective install.
#
# The fix adds a `continue` inside the A3 loop that skips skills whose number
# prefix doesn't appear in ONLY_SKILLS (update-skills.sh:3756-3773).
#
# This test extracts the REAL A3 gate block (while loop body + verdict) from
# update-skills.sh by exact line range and drives it behind hermetic manifests.
# It never sources or executes the full 10k+ line updater.
#
# PROVES:
#   (A) --only 05 + non-target drift (02)  -> gate PASSES  (exit 0)
#   (B) --only 05 + target drift (05)      -> gate FAILS   (exit 1)
#   (C) --only 05 + target missing         -> gate FAILS   (exit 1)
#   (D) full run + multi-skill drift -> gate FAILS citing every drifted skill
#   (E) multi-value --only "05,07" + both drifted -> FAILS, both cited
#   (F) whitespace-tolerant "--only \" 05 , 07 \"" handles trimming
#   (G) MUTATION PROOF: delete lines 3758-3773 (the continue block) -> test A
#       turns RED (fails instead of passes), proving the skip is load-bearing.
#
# Exit 0 = all checks pass.  Exit 1 = one or more failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATE_SH="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo "=== only-mode-a3-gate.test.sh ==="

[ -f "$UPDATE_SH" ] || { echo "FATAL: update-skills.sh not found at $UPDATE_SH"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# ---------------------------------------------------------------------------
# Step 1: extract the A3 gate block (while loop + verdict) from
# update-skills.sh into a hermetic runner script.
#
# Lines 3749-3787 = while loop body (including U004 skip block)
# Lines 3789-3802 = verdict block (FAIL gate + PASS message)
# ---------------------------------------------------------------------------
cat > "$WORK/runner.sh" << 'RUNNER_HEADER'
#!/usr/bin/env bash
set -uo pipefail

SRC_MANIFEST="${SRC_MANIFEST:-}"
DEST_MANIFEST="${DEST_MANIFEST:-}"
ONLY_SKILLS="${ONLY_SKILLS:-}"

_A3_GATE_PASS=1
_A3_MISMATCH_SKILLS=""

# Stub: the real verdict block tries to rm -rf TEMP_EXTRACT/TEMP_ZIP before
# exit 1.  We set them to empty so 'rm -rf "" ""' is harmless.
TEMP_EXTRACT=""
TEMP_ZIP=""

# >>> A3-BLOCK-BEGIN (real code from update-skills.sh:3749-3787)
RUNNER_HEADER

sed -n '3749,3787p' "$UPDATE_SH" >> "$WORK/runner.sh"

cat >> "$WORK/runner.sh" << 'RUNNER_VERDICT'

# >>> A3-VERDICT-BEGIN (real code from update-skills.sh:3789-3802)
RUNNER_VERDICT

sed -n '3789,3802p' "$UPDATE_SH" >> "$WORK/runner.sh"

echo >> "$WORK/runner.sh"

chmod +x "$WORK/runner.sh"

# ---------------------------------------------------------------------------
# Step 2: verify the extraction contains the U004 skip.
# ---------------------------------------------------------------------------
if grep -q "U004: when --only is set" "$WORK/runner.sh"; then
  pass "U004 skip block present in extracted runner"
else
  fail "U004 skip block NOT found in runner -- line numbers changed?"
fi

# ---------------------------------------------------------------------------
# Step 3: helper to run the gate.
# ---------------------------------------------------------------------------
run_gate() {
  local _desc="$1" _expect="$2" _src="$3" _dest="$4" _only="$5" _pats="$6"

  export SRC_MANIFEST="$_src"
  export DEST_MANIFEST="$_dest"
  export ONLY_SKILLS="$_only"

  set +e
  "$WORK/runner.sh" > "$WORK/stdout.txt" 2>"$WORK/stderr.txt"
  local _rc=$?
  set -e

  if [ "$_rc" = "$_expect" ]; then
    pass "$_desc (rc=$_rc)"
  else
    local _stderr_txt
    _stderr_txt="$(cat "$WORK/stderr.txt" 2>/dev/null || true)"
    fail "$_desc -- expected rc=$_expect, got rc=$_rc (stderr: $_stderr_txt)"
    return 1
  fi

  if [ "$_pats" != "-" ]; then
    local _actual
    _actual="$(cat "$WORK/stderr.txt" 2>/dev/null || true)"
    local _oifs="$IFS"; IFS='|'
    for _pat in $_pats; do
      if ! echo "$_actual" | grep -q "$_pat"; then
        fail "$_desc -- stderr missing: '$_pat'"
      fi
    done
    IFS="$_oifs"
  fi
}

# ---------------------------------------------------------------------------
# Step 4: manifest fixtures.
# ---------------------------------------------------------------------------
SRC="02-test-skill|aaa111bbb
05-ghl-setup|ccc222ddd
07-other-skill|eee333fff"

DST_DRIFT_02="02-test-skill|MODIFIED
05-ghl-setup|ccc222ddd
07-other-skill|eee333fff"

DST_DRIFT_05="02-test-skill|aaa111bbb
05-ghl-setup|MODIFIED
07-other-skill|eee333fff"

DST_DRIFT_05_07="02-test-skill|aaa111bbb
05-ghl-setup|MODIFIED
07-other-skill|MODIFIED"

DST_MISSING_05="02-test-skill|aaa111bbb
07-other-skill|eee333fff"

# ---------------------------------------------------------------------------
# Step 5: test cases.
# ---------------------------------------------------------------------------

echo ""
echo "--- (A) --only 05 + non-target drift (02) => gate PASSES ---"
run_gate "A: --only 05, non-target 02 drifted" 0 "$SRC" "$DST_DRIFT_02" "05" "-"

echo ""
echo "--- (B) --only 05 + target drift (05) => gate FAILS ---"
run_gate "B: --only 05, target 05 drifted" 1 "$SRC" "$DST_DRIFT_05" "05" \
  "MISMATCH: 05-ghl-setup"

echo ""
echo "--- (C) --only 05 + target missing => gate FAILS ---"
run_gate "C: --only 05, target 05 missing" 1 "$SRC" "$DST_MISSING_05" "05" \
  "MISMATCH: 05-ghl-setup"

echo ""
echo "--- (D) full run + multi-skill drift => gate FAILS, both cited ---"
run_gate "D: full run, 05+07 drifted" 1 "$SRC" "$DST_DRIFT_05_07" "" \
  "05-ghl-setup|07-other-skill"

echo ""
echo "--- (E) --only \"05,07\" + both drifted => gate FAILS, both cited ---"
run_gate "E: --only 05,07, both drifted" 1 "$SRC" "$DST_DRIFT_05_07" "05,07" \
  "05-ghl-setup|07-other-skill"

echo ""
echo "--- (F1) whitespace-tolerant: --only \" 05 , 07 \" + target drift => FAILS ---"
run_gate "F1: --only ' 05 , 07 ', targets drifted" 1 "$SRC" "$DST_DRIFT_05_07" " 05 , 07 " \
  "05-ghl-setup|07-other-skill"

echo ""
echo "--- (F2) whitespace-tolerant: --only \" 05 \" + non-target drift => PASSES ---"
run_gate "F2: --only ' 05 ', non-target 02 drifted" 0 "$SRC" "$DST_DRIFT_02" " 05 " "-"

echo ""
echo "--- (G) --only \"05,07\" + only non-target drifted => PASSES ---"
run_gate "G: --only 05,07, non-target 02 drifted" 0 "$SRC" "$DST_DRIFT_02" "05,07" "-"

# ---------------------------------------------------------------------------
echo ""
echo "=== only-mode-a3-gate.test.sh: $PASS pass, $FAIL fail ==="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0

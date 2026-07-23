#!/usr/bin/env bash
set -uo pipefail
# ============================================================================
# u121-version-bumper-roll.test.sh -- U121 fleet rollout: version-bumper fix
# ============================================================================
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/fleet-roll/roll-version-bumper-fix.sh"
BUMPER_SOURCE="$REPO_ROOT/scripts/bump-version.sh"

export ROLL_BUMPER_DEVEL=1

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
echo "=== u121-version-bumper-roll.test.sh (U121) ==="; echo ""

[ -f "$SCRIPT" ]        || { echo "FATAL: $SCRIPT missing"; exit 1; }
[ -f "$BUMPER_SOURCE" ] || { echo "FATAL: $BUMPER_SOURCE missing"; exit 1; }

S=$(mktemp -d); trap 'rm -rf $S' EXIT

bumper_has_qc_summary_rewrite() {
  grep -nE '^[^#].*_qc-summary\.md' "$1" >/dev/null 2>&1
}

build_fixture() {
  local dest="$1" mode="$2"
  mkdir -p "${dest}/scripts"
  cp "${BUMPER_SOURCE}" "${dest}/scripts/bump-version.sh"
  chmod +x "${dest}/scripts/bump-version.sh"
  if [ "$mode" = "dirty" ]; then
    echo 'echo "Role Library v${TARGET_NOV}.0.0" > _qc-summary.md' >> "${dest}/scripts/bump-version.sh"
  fi
}

build_missing_fixture() {
  local dest="$1"
  mkdir -p "${dest}/scripts"
}

make_roster() {
  local file="$1" slug="$2" ob_root="$3"
  printf '%s|local|-|%s\n' "$slug" "$ob_root" > "$file"
}

run_roll() {
  local ledger="$S/ledger-$$"
  mkdir -p "$ledger"
  bash "$SCRIPT" "$@" --ledger-dir "$ledger" 2>&1 || true
}

echo "--- T1: parses roster and dry-run flow ---"
F1="$S/t1"; build_fixture "$F1" "clean"
R1="$S/t1-roster.txt"; make_roster "$R1" "testbox" "$F1"
OUT1="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R1" --dry-run)"
echo "$OUT1" | grep -q "plan: 1 box" && pass "T1a: parses roster" || fail "T1a: roster count"
echo "$OUT1" | grep -q "testbox" && pass "T1b: box slug" || fail "T1b: slug"
echo "$OUT1" | grep -q "dry-run" && pass "T1c: dry-run mode" || fail "T1c: mode"

echo "--- T2: dry-run detects clean box ---"
F2="$S/t2"; build_fixture "$F2" "clean"
R2="$S/t2-roster.txt"; make_roster "$R2" "cleanbox2" "$F2"
OUT2="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R2" --dry-run)"
echo "$OUT2" | grep -q "already clean" && pass "T2: clean box detected" || fail "T2: clean not detected"

echo "--- T3: dry-run detects dirty box ---"
F3="$S/t3"; build_fixture "$F3" "dirty"
R3="$S/t3-roster.txt"; make_roster "$R3" "dirtybox3" "$F3"
OUT3="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R3" --dry-run)"
echo "$OUT3" | grep -qE "DIRTY|FAIL" && pass "T3: dirty flagged" || fail "T3: not flagged"

echo "--- T4: --yes mode fixes dirty box ---"
F4="$S/t4"; build_fixture "$F4" "dirty"
R4="$S/t4-roster.txt"; make_roster "$R4" "dbox4" "$F4"
OUT4="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R4" --yes)"
echo "$OUT4" | grep -q "PASS (fixed)" && pass "T4a: fix reported" || fail "T4a: fix not reported"
if bumper_has_qc_summary_rewrite "${F4}/scripts/bump-version.sh"; then
  fail "T4b: qc-summary rewrite still present"
else
  pass "T4b: qc-summary rewrite removed"
fi
ls "${F4}/scripts"/bump-version.sh.bak-pre-bumper-roll-* >/dev/null 2>&1 && pass "T4c: backup" || fail "T4c: no backup"
! bumper_has_qc_summary_rewrite "${F4}/scripts/bump-version.sh" && pass "T4d: clean after fix" || fail "T4d: still dirty"

echo "--- T5: idempotency ---"
F5="$S/t5"; build_fixture "$F5" "dirty"
R5="$S/t5-roster.txt"; make_roster "$R5" "idbox5" "$F5"
OUT5a="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R5" --yes)"
echo "$OUT5a" | grep -q "PASS (fixed)" && pass "T5a: first run fixed" || fail "T5a: first run"
OUT5b="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R5" --yes)"
echo "$OUT5b" | grep -qE "already clean|already-clean" && pass "T5b: re-run already-clean" || fail "T5b: re-run"

echo "--- T6: --only filter ---"
F6c="$S/t6clean"; build_fixture "$F6c" "clean"
F6d="$S/t6dirty"; build_fixture "$F6d" "dirty"
printf 'box-a|local|-|%s\nbox-b|local|-|%s\n' "$F6c" "$F6d" > "$S/t6-roster.txt"
OUT6="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$S/t6-roster.txt" --dry-run --only box-b)"
echo "$OUT6" | grep -qE "DIRTY|FAIL" && pass "T6a: --only box-b saw dirty" || fail "T6a: --only"
echo "$OUT6" | grep -q "box-a" && fail "T6b: box-a leaked" || pass "T6b: box-a excluded"

echo "--- T7: arming pin ---"
F7="$S/t7"; build_fixture "$F7" "dirty"
R7="$S/t7-roster.txt"; make_roster "$R7" "armbox7" "$F7"
OUT7="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R7" 2>&1)"
echo "$OUT7" | grep -qE "arming pin|--yes" && pass "T7: refused w/o --yes" || fail "T7: no pin check"

echo "--- T8: empty roster rejected ---"
printf '' > "$S/t8-empty.txt"
OUT8="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$S/t8-empty.txt" 2>&1)"
echo "$OUT8" | grep -q "empty" && pass "T8: empty rejected" || fail "T8: not rejected"

echo "--- T9: missing bump-version.sh on box ---"
F9="$S/t9"; build_missing_fixture "$F9"
R9="$S/t9-roster.txt"; make_roster "$R9" "missbox9" "$F9"
OUT9="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$R9" --dry-run)"
echo "$OUT9" | grep -q "ERROR" && pass "T9: missing file reported as ERROR" || fail "T9: missing file not error"

echo "--- T10: JSONL ledger ---"
F10="$S/t10"; build_fixture "$F10" "dirty"
R10="$S/t10-roster.txt"; make_roster "$R10" "lbox10" "$F10"
mkdir -p "$S/t10-ledger"
ROLL_BUMPER_SRC_DIR="$REPO_ROOT" bash "$SCRIPT" --roster "$R10" --yes --ledger-dir "$S/t10-ledger" >/dev/null 2>&1
LEDGER_FILE=$(ls "$S/t10-ledger"/bumper-fix-roll-*.jsonl 2>/dev/null | head -1)
if [ -n "${LEDGER_FILE}" ] && [ -s "${LEDGER_FILE}" ]; then
  python3 -c "import json; [json.loads(l) for l in open('${LEDGER_FILE}')]" 2>/dev/null \
    && pass "T10a: valid JSONL" || fail "T10a: invalid JSONL"
  grep -q '"slug"' "${LEDGER_FILE}" && pass "T10b: has slug" || fail "T10b: no slug"
  grep -q '"result"' "${LEDGER_FILE}" && pass "T10c: has result" || fail "T10c: no result"
else
  fail "T10: no ledger"
fi

echo "--- T11: duplicate slug rejected ---"
F11="$S/t11"; build_fixture "$F11" "clean"
printf 'dupbox|local|-|%s\ndupbox|local|-|%s\n' "$F11" "$F11" > "$S/t11-roster.txt"
OUT11="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$S/t11-roster.txt" 2>&1)"
echo "$OUT11" | grep -q "duplicate" && pass "T11: duplicate rejected" || fail "T11: not rejected"

echo "--- T12: bad slug shape rejected ---"
F12="$S/t12"; build_fixture "$F12" "clean"
printf 'BAD SLUG|local|-|%s\n' "$F12" > "$S/t12-roster.txt"
OUT12="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$S/t12-roster.txt" 2>&1)"
echo "$OUT12" | grep -qE "bad slug|malformed" && pass "T12: bad slug rejected" || fail "T12: not rejected"

echo "--- T13: operator source dirty preflight ---"
F13="$S/t13"; build_fixture "$F13" "clean"
F13_DIRTY_SRC="$S/t13-dirty-src"; build_fixture "$F13_DIRTY_SRC" "dirty"
R13="$S/t13-roster.txt"; make_roster "$R13" "t13box" "$F13"
OUT13="$(ROLL_BUMPER_SRC_DIR="$F13_DIRTY_SRC" bash "$SCRIPT" --roster "$R13" --dry-run 2>&1)"
echo "$OUT13" | grep -q "NOT clean" && pass "T13: dirty source preflight caught" || fail "T13: preflight not caught"

echo ""
echo "--- MUTATION PROOF ---"

# M1: Mutate apply_fix copy step to no-op. Dirty box MUST stay dirty.
M1_DIR="$S/m1"; build_fixture "$M1_DIR" "dirty"
M1_SCRIPT="$S/m1-roll.sh"; cp "$SCRIPT" "$M1_SCRIPT"
sed -i '' 's/cp "${BUMPER_SOURCE}" "${tmpfile}"/false # MUTATED no-copy/' "$M1_SCRIPT"
M1_ROSTER="$S/m1-roster.txt"; make_roster "$M1_ROSTER" "mut1" "$M1_DIR"
ROLL_BUMPER_SRC_DIR="$REPO_ROOT" bash "$M1_SCRIPT" --roster "$M1_ROSTER" --yes --ledger-dir "$S/m1-ledger" >/dev/null 2>&1 || true
if bumper_has_qc_summary_rewrite "${M1_DIR}/scripts/bump-version.sh"; then
  pass "M1a: mutated fix did NOT remove qc-summary rewrite (RED)"
else
  fail "M1a: mutation missed (rewrite removed)"
fi

M1R_DIR="$S/m1r"; build_fixture "$M1R_DIR" "dirty"
M1R_ROSTER="$S/m1r-roster.txt"; make_roster "$M1R_ROSTER" "mut1r" "$M1R_DIR"
ROLL_BUMPER_SRC_DIR="$REPO_ROOT" bash "$SCRIPT" --roster "$M1R_ROSTER" --yes --ledger-dir "$S/m1r-ledger" >/dev/null 2>&1
if bumper_has_qc_summary_rewrite "${M1R_DIR}/scripts/bump-version.sh"; then
  fail "M1b: revert still dirty"
else
  pass "M1b: revert GREEN (original script fixed it)"
fi

# M2: Mutate arming-pin guard. Without guard, no --yes still writes.
M2_DIR="$S/m2"; build_fixture "$M2_DIR" "dirty"
M2_SCRIPT="$S/m2-roll.sh"; cp "$SCRIPT" "$M2_SCRIPT"
perl -i -0777 -pe 's/if \[ "\$\{DRY_RUN\}" != "1" ] && \[ "\$\{ARMED\}" != "1" ]; then\n  die "REAL mode requires --yes.*\nfi/if false; then\n  : # MUTATED arming pin disabled\nfi/' "$M2_SCRIPT"
M2_ROSTER="$S/m2-roster.txt"; make_roster "$M2_ROSTER" "mut2" "$M2_DIR"
ROLL_BUMPER_SRC_DIR="$REPO_ROOT" bash "$M2_SCRIPT" --roster "$M2_ROSTER" --ledger-dir "$S/m2-ledger" >/dev/null 2>&1 || true
if bumper_has_qc_summary_rewrite "${M2_DIR}/scripts/bump-version.sh"; then
  M2_CHANGED=0
else
  M2_CHANGED=1
fi
if [ "$M2_CHANGED" -eq 1 ]; then
  pass "M2a: RED -- arming-pin loss allowed write (guard was load-bearing)"
else
  fail "M2a: mutation missed -- rewrite still present (guard removal had no effect)"
fi

M2R_DIR="$S/m2r"; build_fixture "$M2R_DIR" "dirty"
M2R_ROSTER="$S/m2r-roster.txt"; make_roster "$M2R_ROSTER" "mut2r" "$M2R_DIR"
ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$M2R_ROSTER" >/dev/null 2>&1 || true
if bumper_has_qc_summary_rewrite "${M2R_DIR}/scripts/bump-version.sh"; then
  pass "M2b: GREEN -- original guard prevented write (revert restored safety)"
else
  fail "M2b: revert failed -- rewrite was removed by original script"
fi

# M3: Mutate has_dirty_bumper to always return 1 (clean).
M3_DIR="$S/m3"; build_fixture "$M3_DIR" "dirty"
M3_SCRIPT="$S/m3-roll.sh"; cp "$SCRIPT" "$M3_SCRIPT"
sed -i '' '/^has_dirty_bumper() {/a\
  return 1  # MUTATED: always clean
' "$M3_SCRIPT"
M3_ROSTER="$S/m3-roster.txt"; make_roster "$M3_ROSTER" "mut3" "$M3_DIR"
OUT3_MUT="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" bash "$M3_SCRIPT" --roster "$M3_ROSTER" --yes --ledger-dir "$S/m3-ledger" 2>&1)"
if echo "$OUT3_MUT" | grep -qE "already clean|already-clean"; then
  pass "M3a: RED -- mutated check reported dirty box as clean (detection failed)"
else
  fail "M3a: mutation missed -- dirty box was correctly flagged"
fi

M3R_DIR="$S/m3r"; build_fixture "$M3R_DIR" "dirty"
M3R_ROSTER="$S/m3r-roster.txt"; make_roster "$M3R_ROSTER" "mut3r" "$M3R_DIR"
OUT3R="$(ROLL_BUMPER_SRC_DIR="$REPO_ROOT" run_roll --roster "$M3R_ROSTER" --yes)"
echo "$OUT3R" | grep -q "PASS (fixed)" && pass "M3b: GREEN -- revert correctly detected and fixed dirty box" || fail "M3b: revert failed"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
echo "PASS: all U121"
exit 0

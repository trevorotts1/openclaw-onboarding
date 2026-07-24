#!/usr/bin/env bash
set -uo pipefail
# ============================================================================
# u117-wave-list-roll.test.sh -- U117 fleet rollout: wave-list fix to all boxes
# ============================================================================
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/roll-wave-list-fix.sh"
INTEGRITY_CHECK="$REPO_ROOT/scripts/qc-assert-wave-list-integrity.py"
LIB_SOURCE="$REPO_ROOT/lib-onboarding-state.sh"
WATCHDOG="$REPO_ROOT/scripts/watchdog-onboarding-loop.sh"

export ROLL_WAVE_LIST_DEVEL=1
export ROLL_WAVE_LIST_SRC_DIR="$REPO_ROOT"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
echo "=== u117-wave-list-roll.test.sh (U117) ==="; echo ""

# Sanity
[ -f "$SCRIPT" ]          || { echo "FATAL: $SCRIPT missing"; exit 1; }
[ -f "$INTEGRITY_CHECK" ] || { echo "FATAL: $INTEGRITY_CHECK missing"; exit 1; }
[ -f "$LIB_SOURCE" ]      || { echo "FATAL: $LIB_SOURCE missing"; exit 1; }
[ -f "$WATCHDOG" ]        || { echo "FATAL: $WATCHDOG missing"; exit 1; }

S=$(mktemp -d); trap 'rm -rf $S' EXIT

# Check if wave list is dirty (contains phantom "11-superdesign" in OC_WAVE2_SKILLS)
wave_list_has_phantom() {
  grep -q '^OC_WAVE2_SKILLS=.*11-superdesign' "$1" 2>/dev/null
}

# Build a test fixture "box" with an onboarding clone.
# mode: "clean" (valid wave lists) or "dirty" (has phantom 11-superdesign).
build_fixture() {
  local dest="$1" mode="$2"
  mkdir -p "${dest}/scripts"

  # Copy integrity checker
  cp "${INTEGRITY_CHECK}" "${dest}/scripts/qc-assert-wave-list-integrity.py"
  chmod +x "${dest}/scripts/qc-assert-wave-list-integrity.py"
  # Copy watchdog (integrity check needs it)
  cp "${WATCHDOG}" "${dest}/scripts/watchdog-onboarding-loop.sh"

  # Create skill dirs for all wave entries
  for d in \
    01-teach-yourself-protocol 02-back-yourself-up-protocol \
    03-agent-browser 04-superpowers 05-ghl-setup 06-ghl-install-pages \
    07-kie-setup 08-vercel-setup 09-context7 10-github-setup \
    12-openrouter-setup 14-google-workspace-integration 63-agnes-image \
    15-blackceo-team-management 16-summarize-youtube 17-self-improving-agent \
    18-proactive-agent 19-humanizer 20-youtube-watcher 24-storyboard-writer \
    25-video-creator 26-caption-creator 27-video-editor 28-cinematic-forge \
    29-ghl-convert-and-flow 30-fish-audio-api-reference 64-agnes-video \
    43-graphify-knowledge-graph \
    31-upgraded-memory-system 36-ghl-mcp-setup \
    22-book-to-persona-coaching-leadership-system 23-ai-workforce-blueprint \
    32-command-center-setup 35-social-media-planner \
    44-convert-and-flow-operator 45-design-intelligence-library \
    47-movie-producer 48-facebook-ad-generator 49-signature-funnel \
    50-email-engine 51-signature-presentation 52-avatar-alchemist \
    53-book-writer 54-anthology-writer 55-product-bio \
    56-sales-page-assets 57-social-media-in-a-box; do
    mkdir -p "${dest}/${d}"
  done

  if [ "$mode" = "dirty" ]; then
    mkdir -p "${dest}/11-superdesign-ARCHIVED"
  fi

  # Write lib-onboarding-state.sh via Python (suppress SyntaxWarning on older Pythons)
  python3 2>/dev/null << PYEOF
waves = {
    1: '01-teach-yourself-protocol 02-back-yourself-up-protocol',
    2: '03-agent-browser 04-superpowers 05-ghl-setup 06-ghl-install-pages 07-kie-setup 08-vercel-setup 09-context7 10-github-setup 12-openrouter-setup 14-google-workspace-integration 63-agnes-image',
    3: '15-blackceo-team-management 16-summarize-youtube 17-self-improving-agent 18-proactive-agent 19-humanizer 20-youtube-watcher 24-storyboard-writer 25-video-creator 26-caption-creator 27-video-editor 28-cinematic-forge 29-ghl-convert-and-flow 30-fish-audio-api-reference 64-agnes-video 43-graphify-knowledge-graph',
    4: '31-upgraded-memory-system 36-ghl-mcp-setup',
    5: '22-book-to-persona-coaching-leadership-system 23-ai-workforce-blueprint 32-command-center-setup 35-social-media-planner',
    6: '44-convert-and-flow-operator 45-design-intelligence-library 47-movie-producer 48-facebook-ad-generator 49-signature-funnel 50-email-engine 51-signature-presentation 52-avatar-alchemist 53-book-writer 54-anthology-writer 55-product-bio 56-sales-page-assets 57-social-media-in-a-box',
}
if '$mode' == 'dirty':
    waves[2] = waves[2] + ' 11-superdesign'
out = ['#!/usr/bin/env bash', '# test fixture']
for n in range(1,7):
    out.append('OC_WAVE' + str(n) + '_SKILLS="' + waves[n] + '"')
with open('${dest}/lib-onboarding-state.sh','w') as f:
    f.write(chr(10).join(out) + chr(10))
PYEOF
}

make_roster() {
  local file="$1" slug="$2" ob_root="$3"
  printf '%s|local|-|%s\n' "$slug" "$ob_root" > "$file"
}

run_roll() {
  local ledger="$S/ledger-$$"
  mkdir -p "$ledger"
  env ROLL_WAVE_LIST_DEVEL=1 ROLL_WAVE_LIST_SRC_DIR="$REPO_ROOT" \
    bash "$SCRIPT" "$@" --ledger-dir "$ledger" 2>&1 || true
}

echo "--- T1: parses roster and dry-run flow ---"
F1="$S/t1"; build_fixture "$F1" "clean"
R1="$S/t1-roster.txt"; make_roster "$R1" "testbox" "$F1"
OUT1="$(run_roll --roster "$R1" --dry-run)"
echo "$OUT1" | grep -q "plan: 1 box" && pass "T1a: parses roster" || fail "T1a: roster count"
echo "$OUT1" | grep -q "testbox" && pass "T1b: box slug" || fail "T1b: slug"
echo "$OUT1" | grep -q "dry-run" && pass "T1c: dry-run mode" || fail "T1c: mode"

echo "--- T2: dry-run detects clean box ---"
F2="$S/t2"; build_fixture "$F2" "clean"
R2="$S/t2-roster.txt"; make_roster "$R2" "cleanbox2" "$F2"
OUT2="$(run_roll --roster "$R2" --dry-run)"
# A clean box in dry-run mode should show the box in the "pass:" line of the summary
echo "$OUT2" | grep -q "^  pass:.*cleanbox2" && pass "T2: clean box in pass list" || fail "T2: clean box not in pass list"

echo "--- T3: dry-run detects dirty box ---"
F3="$S/t3"; build_fixture "$F3" "dirty"
R3="$S/t3-roster.txt"; make_roster "$R3" "dirtybox3" "$F3"
OUT3="$(run_roll --roster "$R3" --dry-run)"
echo "$OUT3" | grep -q "FAIL" && pass "T3: dirty flagged" || fail "T3: not flagged"

echo "--- T4: --yes mode fixes dirty box ---"
F4="$S/t4"; build_fixture "$F4" "dirty"
R4="$S/t4-roster.txt"; make_roster "$R4" "dbox4" "$F4"
OUT4="$(run_roll --roster "$R4" --yes)"
echo "$OUT4" | grep -q "PASS (fixed)" && pass "T4a: fix reported" || fail "T4a: fix not reported"
if wave_list_has_phantom "${F4}/lib-onboarding-state.sh"; then
  fail "T4b: phantom still present"
else
  pass "T4b: phantom removed"
fi
ls "${F4}"/lib-onboarding-state.sh.bak-pre-wave-list-roll-* >/dev/null 2>&1 && pass "T4c: backup" || fail "T4c: no backup"
python3 "${INTEGRITY_CHECK}" --root "$F4" >/dev/null 2>&1 && pass "T4d: integrity PASS" || fail "T4d: integrity FAIL"

echo "--- T5: idempotency ---"
F5="$S/t5"; build_fixture "$F5" "dirty"
R5="$S/t5-roster.txt"; make_roster "$R5" "idbox5" "$F5"
OUT5a="$(run_roll --roster "$R5" --yes)"
echo "$OUT5a" | grep -q "PASS (fixed)" && pass "T5a: first run fixed" || fail "T5a: first run"
OUT5b="$(run_roll --roster "$R5" --yes)"
echo "$OUT5b" | grep -q "already clean\|already-clean" && pass "T5b: re-run already-clean" || fail "T5b: re-run"

echo "--- T6: --only filter ---"
F6c="$S/t6clean"; build_fixture "$F6c" "clean"
F6d="$S/t6dirty"; build_fixture "$F6d" "dirty"
printf 'box-a|local|-|%s\nbox-b|local|-|%s\n' "$F6c" "$F6d" > "$S/t6-roster.txt"
OUT6="$(run_roll --roster "$S/t6-roster.txt" --dry-run --only box-b)"
echo "$OUT6" | grep -q "FAIL" && pass "T6a: --only box-b saw dirty" || fail "T6a: --only"
echo "$OUT6" | grep -q "box-a" && fail "T6b: box-a leaked" || pass "T6b: box-a excluded"

echo "--- T7: arming pin ---"
F7="$S/t7"; build_fixture "$F7" "dirty"
R7="$S/t7-roster.txt"; make_roster "$R7" "armbox7" "$F7"
OUT7="$(run_roll --roster "$R7" 2>&1)"
echo "$OUT7" | grep -q "arming pin\|--yes" && pass "T7: refused w/o --yes" || fail "T7: no pin check"

echo "--- T8: empty roster rejected ---"
printf '' > "$S/t8-empty.txt"
OUT8="$(run_roll --roster "$S/t8-empty.txt" 2>&1)"
echo "$OUT8" | grep -q "empty" && pass "T8: empty rejected" || fail "T8: not rejected"

echo "--- T9: JSONL ledger ---"
F9="$S/t9"; build_fixture "$F9" "dirty"
R9="$S/t9-roster.txt"; make_roster "$R9" "lbox9" "$F9"
mkdir -p "$S/t9-ledger"
env ROLL_WAVE_LIST_DEVEL=1 ROLL_WAVE_LIST_SRC_DIR="$REPO_ROOT" \
  bash "$SCRIPT" --roster "$R9" --yes --ledger-dir "$S/t9-ledger" >/dev/null 2>&1
LEDGER_FILE=$(ls "$S/t9-ledger"/wave-list-roll-*.jsonl 2>/dev/null | head -1)
if [ -n "${LEDGER_FILE}" ] && [ -s "${LEDGER_FILE}" ]; then
  python3 -c "import json; [json.loads(l) for l in open('${LEDGER_FILE}')]" 2>/dev/null \
    && pass "T9a: valid JSONL" || fail "T9a: invalid JSONL"
  grep -q '"slug"' "${LEDGER_FILE}" && pass "T9b: has slug" || fail "T9b: no slug"
  grep -q '"result"' "${LEDGER_FILE}" && pass "T9c: has result" || fail "T9c: no result"
else
  fail "T9: no ledger"
fi

echo ""
echo "--- MUTATION PROOF ---"

# M1: Mutate the fix to NOT copy (replace cp with false in apply_fix).
# A dirty box should STAY dirty. Then revert to prove original script fixes it.
M1_DIR="$S/m1"; build_fixture "$M1_DIR" "dirty"
M1_SCRIPT="$S/m1-roll.sh"; cp "$SCRIPT" "$M1_SCRIPT"
python3 -c "
s = open('${M1_SCRIPT}').read()
# Strip the core fix logic: remove the whole apply_fix body after the backup,
# making it a no-op that returns 1. Replace 3 lines of the fix block.
old = 'cp \"\${LIB_SOURCE}\" \"\${tmpfile}\" || {\n    cp -p \"\${backup}\" \"\${lib_file}\"\n    rm -f \"\${tmpfile}\"\n    echo \"REMOTE-ERROR: copy source failed\"; echo \"RESULT=FAIL\"; return 1\n  }'
new = 'echo \"REMOTE-ERROR: MUTATED fix disabled (no copy)\"; echo \"RESULT=FAIL\"; return 1'
s = s.replace(old, new, 1)
open('${M1_SCRIPT}','w').write(s)
" 2>/dev/null
M1_ROSTER="$S/m1-roster.txt"; make_roster "$M1_ROSTER" "mut1" "$M1_DIR"
bash "$M1_SCRIPT" --roster "$M1_ROSTER" --yes --ledger-dir "$S/m1-ledger" >/dev/null 2>&1 || true
if wave_list_has_phantom "${M1_DIR}/lib-onboarding-state.sh"; then
  pass "M1a: mutated fix did NOT remove phantom (RED)"
else
  fail "M1a: mutation missed (phantom removed)"
fi

# Revert: original script on fresh dirty box -> should fix
M1R_DIR="$S/m1r"; build_fixture "$M1R_DIR" "dirty"
M1R_ROSTER="$S/m1r-roster.txt"; make_roster "$M1R_ROSTER" "mut1r" "$M1R_DIR"
env ROLL_WAVE_LIST_DEVEL=1 ROLL_WAVE_LIST_SRC_DIR="$REPO_ROOT" \
  bash "$SCRIPT" --roster "$M1R_ROSTER" --yes --ledger-dir "$S/m1r-ledger" >/dev/null 2>&1
if wave_list_has_phantom "${M1R_DIR}/lib-onboarding-state.sh"; then
  fail "M1b: revert still dirty"
else
  pass "M1b: revert GREEN (original script fixed it)"
fi

# M2: Mutate arming-pin guard. Remove the die check.
# Without --yes and without the guard, the script WILL write (DRY_RUN=0 is default).
# This is the RED state -- proves the guard is load-bearing.
# Then revert to original to prove GREEN.
M2_DIR="$S/m2"; build_fixture "$M2_DIR" "dirty"
M2_SCRIPT="$S/m2-roll.sh"; cp "$SCRIPT" "$M2_SCRIPT"
python3 -c "
s = open('${M2_SCRIPT}').read()
old = 'if [ \"\${DRY_RUN}\" != \"1\" ] && [ \"\${ARMED}\" != \"1\" ]; then\n  die \"REAL mode requires --yes (the arming pin). Re-run with --dry-run to rehearse, or add --yes to write.\"\nfi'
new = 'if false; then\n  : # MUTATED: arming pin disabled\nfi'
s = s.replace(old, new, 1)
open('${M2_SCRIPT}','w').write(s)
" 2>/dev/null
M2_ROSTER="$S/m2-roster.txt"; make_roster "$M2_ROSTER" "mut2" "$M2_DIR"
bash "$M2_SCRIPT" --roster "$M2_ROSTER" --ledger-dir "$S/m2-ledger" >/dev/null 2>&1 || true
if wave_list_has_phantom "${M2_DIR}/lib-onboarding-state.sh"; then
  M2_CHANGED=0
else
  M2_CHANGED=1
fi
# RED detection: mutation should cause write without permission
if [ "$M2_CHANGED" -eq 1 ]; then
  pass "M2a: RED -- arming-pin loss allowed write (guard was load-bearing)"
else
  fail "M2a: mutation missed -- phantom still present (guard removal had no effect)"
fi

# Revert: fresh dirty box + original script + no --yes -> should NOT write (T7 proves this)
M2R_DIR="$S/m2r"; build_fixture "$M2R_DIR" "dirty"
M2R_ROSTER="$S/m2r-roster.txt"; make_roster "$M2R_ROSTER" "mut2r" "$M2R_DIR"
run_roll --roster "$M2R_ROSTER" >/dev/null 2>&1 || true
if wave_list_has_phantom "${M2R_DIR}/lib-onboarding-state.sh"; then
  pass "M2b: GREEN -- original guard prevented write (revert restored safety)"
else
  fail "M2b: revert failed -- phantom was removed by original script"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
echo "PASS: all U117"
exit 0

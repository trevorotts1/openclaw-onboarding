#!/usr/bin/env bash
# tests/unit/update-skills-verify-ordering.test.sh
# ---------------------------------------------------------------------------
# THE DEFECT. update-skills.sh ran each skill's post-copy verify.sh INSIDE the
# per-skill copy loop, so a skill was verified before its higher-numbered
# siblings had been copied in the same run. A skill whose verify reads a later
# sibling therefore reported a false "[verify] WARN: ... FAILED" during the
# update, even though the same verify.sh passed by hand once the install
# finished. Measured shape: 49-signature-funnel imports from the 71 and 83
# skill folders (and its entry script hard-fails on a missing 83 tree).
#
# THE FIX. The copy loop QUEUES the skill names that ship a verify.sh and the
# pass immediately after the loop runs them in one go, once every skill folder
# is on disk. WARN-and-continue is unchanged: a failing verify still prints the
# same "[verify] WARN: <skill> post-copy verify.sh FAILED -- continuing" line
# and never aborts the update (including under set -e).
#
# METHOD. Like the sibling tests/unit/update-skills-*.test.sh suites, this does
# NOT reimplement the block: it extracts the REAL copy loop VERBATIM from
# update-skills.sh (from its `for SKILL_DIR in "$EXTRACTED_DIR"/[0-9]*/; do`
# line through its own closing `done`) plus the REAL post-copy verify pass
# between its POST-COPY-VERIFY-PASS markers, and runs them against fixture
# skills. If those anchors drift the suite fails loudly (exit 2) rather than
# silently testing nothing. On a tree WITHOUT the fix the pass block is absent,
# which is itself reported and is what makes the behavioural checks below fail.
#
# The fixture skills reproduce the real dependency: 01-early's verify.sh exits
# non-zero unless the later-numbered 02-later folder is already installed. This
# test therefore FAILS on the pre-fix (inline-verify) tree and PASSES with the
# fix.
#
# FULLY OFFLINE: fixture skills only. No network, no gateway, no cron, no
# service, and nothing under the real $HOME or a real skills folder is read or
# written (the harness only ever touches its own mktemp sandbox).
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }

WORK="$(mktemp -d -t verify-ordering-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

COPY_LOOP_START='  for SKILL_DIR in "$EXTRACTED_DIR"/[0-9]*/; do'

# --- verbatim extraction of the real copy loop, start line through its own
#     closing 2-space `done` (no inner block closes at that indentation). -----
awk -v start="$COPY_LOOP_START" '
  $0 == start { p=1 }
  p { print }
  p && $0 == "  done" { exit }
' "$UPDATER" > "$WORK/copyloop.inc"
if [ ! -s "$WORK/copyloop.inc" ] || [ "$(tail -n 1 "$WORK/copyloop.inc")" != "  done" ]; then
  echo "FATAL: could not extract the real copy loop from update-skills.sh (anchor drift?)"
  exit 2
fi
{
  echo 'run_copy_loop() {'
  cat "$WORK/copyloop.inc"
  echo '}'
} > "$WORK/copyloop.sh"
bash -n "$WORK/copyloop.sh" || { echo "FATAL: extracted copy loop does not parse"; exit 2; }

# --- verbatim extraction of the post-copy verify pass (absent before the fix).
awk -v b=">>> POST-COPY-VERIFY-PASS-BEGIN" -v e="<<< POST-COPY-VERIFY-PASS-END" '
  index($0, b) { p=1; next }
  index($0, e) { p=0 }
  p { print }
' "$UPDATER" > "$WORK/postpass.inc"
HAVE_POSTPASS=1
if [ ! -s "$WORK/postpass.inc" ]; then
  HAVE_POSTPASS=0
fi
{
  echo 'run_post_verify_pass() {'
  if [ "$HAVE_POSTPASS" = "1" ]; then cat "$WORK/postpass.inc"; else echo '  : # no post-copy pass on this tree'; fi
  echo '}'
} > "$WORK/postpass.sh"
bash -n "$WORK/postpass.sh" || { echo "FATAL: post-copy pass block does not parse"; exit 2; }

echo "== static: the verify call no longer lives inside the copy loop =="
if grep -qF 'verify.sh" >>"${LOG_FILE:-/dev/null}" 2>&1; then' "$WORK/copyloop.inc"; then
  bad "the copy loop STILL runs verify.sh inline -- ordering defect present"
else
  ok "the copy loop no longer runs verify.sh inline; it only queues the skill name"
fi
if grep -q '_POST_COPY_VERIFY_QUEUE' "$WORK/copyloop.inc"; then
  ok "the copy loop queues each skill that ships a verify.sh"
else
  bad "the copy loop does not queue verify candidates (queue variable missing)"
fi
if [ "$HAVE_POSTPASS" = "1" ]; then
  ok "a post-copy verify pass exists after the loop (POST-COPY-VERIFY-PASS markers found)"
  grep -q '\[verify\] WARN' "$WORK/postpass.inc" \
    && ok "the post-copy pass keeps the original WARN-and-continue line" \
    || bad "the post-copy pass does not emit the original [verify] WARN line"
  grep -q 'for _PCV_SKILL in \$_POST_COPY_VERIFY_QUEUE' "$WORK/postpass.inc" \
    && ok "the post-copy pass iterates the queue the loop filled" \
    || bad "the post-copy pass does not iterate the queue"
else
  bad "NO post-copy verify pass exists -- verify.sh still runs inside the copy loop (pre-fix tree)"
fi

# --- fixture skills --------------------------------------------------------
# 01-early mimics 49-signature-funnel: its verify needs the LATER 02-later
# folder to exist. 02-later is the sibling (71/83 stand-in). 03-broken always
# fails, proving WARN-and-continue survives under set -e.
build_fixtures() {
  local root="$1"
  mkdir -p "$root/01-early/scripts" "$root/02-later/scripts" "$root/03-broken/scripts"
  cat > "$root/01-early/verify.sh" <<'FIX'
#!/usr/bin/env bash
# fixture: needs the higher-numbered sibling folder to be installed first
rc=0
[ -d "${SKILLS_DIR}/02-later" ] || rc=1
printf '01-early rc=%s\n' "$rc" >> "$FIXTURE_VERIFY_LOG"
if [ "$rc" = "0" ]; then
  echo "01-early: sibling 02-later present"
else
  echo "01-early: MISSING sibling 02-later" >&2
  exit 1
fi
FIX
  cat > "$root/02-later/verify.sh" <<'FIX'
#!/usr/bin/env bash
printf '02-later rc=0\n' >> "$FIXTURE_VERIFY_LOG"
echo "02-later: ok"
FIX
  cat > "$root/03-broken/verify.sh" <<'FIX'
#!/usr/bin/env bash
printf '03-broken rc=1\n' >> "$FIXTURE_VERIFY_LOG"
echo "03-broken: deliberate fixture failure" >&2
exit 1
FIX
  chmod +x "$root"/*/verify.sh
  echo "01-early body"  > "$root/01-early/SKILL.md"
  echo "02-later body"  > "$root/02-later/SKILL.md"
  echo "03-broken body" > "$root/03-broken/SKILL.md"
  echo "keep" > "$root/01-early/scripts/keep.txt"
}

EXTRACTED="$WORK/extracted"
build_fixtures "$EXTRACTED"

# --- harness: run the REAL extracted loop, then the REAL post-copy pass, in a
#     subshell under the SAME `set -euo pipefail` the real updater uses. -------
# stub the box-state helpers the real loop calls (they are not under test here).
write_lib() {
  {
    echo 'oc_skill_box_state_save()  { :; }'
    echo 'oc_skill_box_state_restore() { :; }'
    echo 'oc_remove_tree_guarded() { rm -rf "$1"; }'
    echo 'obs_set_status() { :; }'
    cat "$WORK/copyloop.sh"
    cat "$WORK/postpass.sh"
  } > "$WORK/lib.sh"
  bash -n "$WORK/lib.sh" || { echo "FATAL: assembled harness library does not parse"; exit 2; }
}
write_lib

# run_phases <case_dir> <loop|all>  -> captures stdout+stderr, prints the rc
run_phases() {
  local case_dir="$1" phases="$2"
  local skills="$case_dir/skills"
  mkdir -p "$skills"
  : > "$case_dir/verify.log"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/lib.sh"
    SKILLS_DIR="$skills"
    EXTRACTED_DIR="$EXTRACTED"
    ONLY_SKILLS=""
    NEW_SKILLS_CSV=""
    SKIPPED_COUNT=0
    LOG_FILE="$case_dir/update.log"
    _POST_COPY_VERIFY_QUEUE=""
    FIXTURE_VERIFY_LOG="$case_dir/verify.log"
    export SKILLS_DIR FIXTURE_VERIFY_LOG
    : > "$LOG_FILE"
    if [ "$phases" = "loop" ]; then
      run_copy_loop
    else
      run_copy_loop
      run_post_verify_pass
    fi
    echo "PHASE_END=1"
  ) > "$case_dir/out.txt" 2>&1
  echo "$?"
}

echo ""
echo "== phase A: the copy loop alone (pre-fix behaviour is visible here) =="
A="$WORK/phase-a"; mkdir -p "$A"
RC_A="$(run_phases "$A" loop)"
[ "$RC_A" = "0" ] && ok "(A) the copy loop itself completes under set -e (rc=0)" \
  || bad "(A) the copy loop aborted (rc=$RC_A): $(tail -3 "$A/out.txt" 2>/dev/null)"
grep -q '^PHASE_END=1$' "$A/out.txt" && ok "(A) the copy loop ran to completion" \
  || bad "(A) the copy loop did not reach its end"
if grep -q '\[verify\] WARN: 01-early' "$A/out.txt"; then
  bad "(A) ORDERING DEFECT: 01-early was verified DURING the loop, before sibling 02-later was copied"
else
  ok "(A) nothing is verified during the loop, so no skill can be verified before its later siblings"
fi
for s in 01-early 02-later 03-broken; do
  [ -d "$A/skills/$s" ] && ok "(A) $s was copied" || bad "(A) $s was not copied by the loop"
done

echo ""
echo "== phase B: the loop plus the post-copy verify pass (the fix) =="
B="$WORK/phase-b"; mkdir -p "$B"
RC_B="$(run_phases "$B" all)"
[ "$RC_B" = "0" ] && ok "(B) the whole sequence completes under set -e (rc=0) -- WARN never aborts the update" \
  || bad "(B) the sequence aborted (rc=$RC_B): $(tail -3 "$B/out.txt" 2>/dev/null)"
grep -q '^PHASE_END=1$' "$B/out.txt" && ok "(B) execution reached the end of the sequence" \
  || bad "(B) execution did not reach the end"

EARLY_FINAL="$(grep '^01-early rc=' "$B/verify.log" 2>/dev/null | tail -n 1)"
if [ "$EARLY_FINAL" = "01-early rc=0" ]; then
  ok "(B) 01-early was verified only AFTER 02-later existed (final verify rc=0)"
else
  bad "(B) 01-early's final verify was '${EARLY_FINAL:-<never ran>}' (expected rc=0) -- it was still verified too early"
fi
grep -q '^02-later rc=0$' "$B/verify.log" 2>/dev/null \
  && ok "(B) 02-later was verified after the copy (rc=0)" \
  || bad "(B) 02-later was never verified"
grep -q '^03-broken rc=1$' "$B/verify.log" 2>/dev/null \
  && ok "(B) 03-broken was attempted (a failing verify is still RUN, not skipped)" \
  || bad "(B) 03-broken was never attempted"
if [ "$HAVE_POSTPASS" = "1" ]; then
  grep -q '\[verify\] WARN: 03-broken post-copy verify.sh FAILED -- continuing' "$B/out.txt" \
    && ok "(B) a failing verify still reports the original WARN-and-continue line, naming the skill" \
    || bad "(B) the WARN-and-continue line for the failing fixture is missing"
  grep -q '\[verify\] WARN: 01-early' "$B/out.txt" \
    && bad "(B) 01-early still reported FAILED even though its sibling was installed -- ordering not fixed" \
    || ok "(B) 01-early reported no false FAILED once its later sibling was on disk"
  grep -q '\[verify\] WARN: 02-later' "$B/out.txt" \
    && bad "(B) 02-later unexpectedly reported FAILED" \
    || ok "(B) 02-later reported no FAILED"
fi

echo ""
echo "== phase C: negative control -- the fixture genuinely depends on the later sibling =="
# Prove the fixture is discriminating: with 02-later removed the same verify.sh
# must fail. Otherwise phase B would pass on a fixture that cannot fail at all.
C="$WORK/phase-c"; mkdir -p "$C/skills"
cp -R "$EXTRACTED/01-early" "$C/skills/01-early"
: > "$C/verify.log"
(
  SKILLS_DIR="$C/skills"
  FIXTURE_VERIFY_LOG="$C/verify.log"
  export SKILLS_DIR FIXTURE_VERIFY_LOG
  bash "$C/skills/01-early/verify.sh"
) >"$C/out.txt" 2>&1
RC_C=$?
[ "$RC_C" -ne 0 ] && ok "(C) NEGATIVE CONTROL: with 02-later absent, 01-early's verify fails (rc=$RC_C)" \
  || bad "(C) NEGATIVE CONTROL FAILED: 01-early's verify passed without its sibling, so it cannot detect the ordering bug"
[ "$RC_B" -eq 0 ] && [ "$RC_A" -eq 0 ] && ok "(C) the control failing while phases A/B pass proves the checks discriminate" \
  || bad "(C) a phase above did not complete, so the control proves nothing"

echo ""
echo "== phase D: skill75-style extraction -- the copy body must not need the queue initialised =="
# tests/unit/updater-preserves-skill75-interrupt-state.test.sh extracts the copy
# body with its own anchors (below the queue's initialisation line) and runs it
# under set -euo pipefail. A queue append that reads an unset variable therefore
# kills that simulation with "unbound variable" even though the real updater
# initialises the queue above the extraction anchor. Both an unset and a set
# queue are exercised so the fix cannot hide a second failure.
awk '/^    # Remove old version if exists\./{on=1} on{print} on && /echo "    Updated: \$SKILL_NAME"/{exit}' "$UPDATER" > "$WORK/skillsnippet.inc"
if [ ! -s "$WORK/skillsnippet.inc" ]; then
  echo "FATAL: could not extract the skill75-style copy body (anchor drift?)"
  exit 2
fi
SNIP_SKILLS="$WORK/snippet-skills"
SNIP_RELEASE="$WORK/snippet-release/01-snippet"
mkdir -p "$SNIP_SKILLS" "$SNIP_RELEASE"
printf '#!/usr/bin/env bash\nexit 0\n' > "$SNIP_RELEASE/verify.sh"
echo 'snippet body' > "$SNIP_RELEASE/SKILL.md"
{
  echo 'oc_skill_box_state_save()  { :; }'
  echo 'oc_skill_box_state_restore() { :; }'
  echo 'oc_remove_tree_guarded() { rm -rf "$1"; }'
  echo 'obs_set_status() { :; }'
  echo 'install_one_skill() {'
  cat "$WORK/skillsnippet.inc"
  echo '}'
} > "$WORK/skillsnippet.sh"
bash -n "$WORK/skillsnippet.sh" || { echo "FATAL: skill75-style extracted copy body does not parse"; exit 2; }

run_snippet() {  # $1 = unset|set -> rc; output captured in $WORK/snippet-$1.out
  (
    set -euo pipefail
    . "$WORK/skillsnippet.sh"
    SKILLS_DIR="$SNIP_SKILLS"
    SKILL_DIR="$SNIP_RELEASE/"
    SKILL_NAME=01-snippet
    if [ "$1" = "set" ]; then _POST_COPY_VERIFY_QUEUE=""; else unset _POST_COPY_VERIFY_QUEUE; fi
    install_one_skill
  ) >"$WORK/snippet-$1.out" 2>&1
}

for _case in unset set; do
  rc=0; run_snippet "$_case" || rc=$?
  if grep -q 'unbound variable' "$WORK/snippet-$_case.out"; then
    bad "(D) copy body with the queue $_case aborts on 'unbound variable' (the skill75 simulation would die)"
  elif [ "$rc" -ne 0 ]; then
    bad "(D) copy body with the queue $_case exited non-zero (rc=$rc) without an unbound-variable message"
  else
    ok "(D) copy body finishes clean with the queue $_case (no unbound variable, rc=0)"
  fi
done

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1

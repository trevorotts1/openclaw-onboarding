#!/usr/bin/env bash
# ============================================================================
# updater-preserves-skill-box-state.test.sh
#
# THE DEFECT THIS LOCKS (measured 2026-09-23 on a live client box, v25.1.81).
# update-skills.sh replaces every numbered skill WHOLESALE (guarded remove,
# then cp -r). Skill 59 keeps its per-box resolved tier map, with the owner's
# owner_pins, at 59-anthology-engine/model-map.json, INSIDE that folder. Every
# update deleted the pins, the wiring pass re-resolved with no pins, JUDGE fell
# onto the HEAVY-WRITER model and the log said
#   Model-map re-resolve FAILED CLOSED for 59-anthology-engine
# (AF-AE-JUDGE-INDEPENDENCE). The updater's own backup still held the pin.
#
# THE CONTRACT UNDER TEST
#   1. After a simulated update, 59-anthology-engine/model-map.json still
#      carries the owner_pins it had before.
#   2. The skill's own re-resolve (preflight.sh, exactly as the wiring pass
#      runs it) then PASSES, logs every pin as honored, keeps JUDGE independent
#      of HEAVY-WRITER and carries owner_pins forward again.
#   3. KNOWN-GOOD CONTROL: the same client config with NO pins fails closed on
#      AF-AE-JUDGE-INDEPENDENCE. Without it case 2 could pass for the wrong
#      reason (a config that never needed the pin).
#   4. A path the release SHIPS is never overwritten by preserved box state.
#   5. A file NOT on the allow-list is still removed by the wholesale replace.
#   6. The stash can never be orphaned. When the run dies between save and
#      restore -- oc_remove_tree_guarded refusing with exit 1 on an intact
#      tree, refusing after a PARTIAL removal, or cp -r failing under set -e --
#      main's EXIT trap puts back whatever was taken and removes the stash.
#   7. An allow-listed path containing spaces is preserved intact.
#   8. The update lock is ALWAYS released and the script's own exit status
#      is kept, even when the stash cleanup itself fails (rm refused), on
#      both the exit path and the normal path, and the log names the stash.
#
# METHOD. The wipe+copy step is EXTRACTED VERBATIM from the updater's skill
# install loop (between the "# Remove old version if exists." anchor and the
# "Updated: $SKILL_NAME" echo, both present since before the fix), so running
# this suite with UPDATER_UNDER_TEST=<old update-skills.sh> reproduces the
# defect. main's `trap ... EXIT` line is extracted verbatim too, so the exit
# cases exercise the real trap wiring. oc_remove_tree_guarded is stubbed (a
# plain rm -rf, or a simulated refusal): its own guard has its own suite, this
# one tests what survives the replace.
#
# SAFETY. Everything runs inside mktemp -d with HOME pointed there, so
# preflight.sh never sources the real box secrets file. No network, no box.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
TARGET="${UPDATER_UNDER_TEST:-$REPO/update-skills.sh}"
SKILL=59-anthology-engine

PASS=0; FAIL=0
ok()  { printf '  PASS: %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n== %s ==\n' "$1"; }

[ -f "$TARGET" ] || { echo "FATAL: $TARGET not found"; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 required"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- verbatim extraction ------------------------------------------------------
LIB="$WORK/lib.sh"
{
  echo 'oc_remove_tree_guarded() { rm -rf "$1"; }'
  # The real lock release and main's EXIT-trap wrapper, verbatim. Each run
  # below holds the mkdir-style lock (the macOS path), the one that leaks
  # when the release is skipped; a flock fd would close with the process.
  awk '/^release_update_lock\(\) *\{/,/^}/' "$TARGET"
  awk '/^oc_update_exit_trap\(\) *\{/,/^}/' "$TARGET"
  # The helpers exist only after the fix; absent on the old updater, which is
  # fine because its install step never calls them.
  awk '/^# >>> SKILL-BOX-STATE-BEGIN/{on=1} on{print} /^# <<< SKILL-BOX-STATE-END/{on=0}' "$TARGET"
  echo 'install_one_skill() {'
  awk '/^    # Remove old version if exists\./{on=1} on{print} on && /echo "    Updated: \$SKILL_NAME"/{exit}' "$TARGET"
  echo '}'
} > "$LIB"
grep -q 'cp -r "${SKILL_DIR%/}" "$SKILLS_DIR/"' "$LIB" \
  || { echo "FATAL: install-loop anchors drifted; nothing extracted from $TARGET"; exit 2; }
bash -n "$LIB" || { echo "FATAL: extracted block does not parse"; exit 2; }
# main's EXIT trap, verbatim (the only `trap ... EXIT` in main).
TRAP_LINE="$(awk '/^main\(\) *\{/{on=1} on && /^  trap .* EXIT$/{print; exit}' "$TARGET")"
[ -n "$TRAP_LINE" ] || { echo "FATAL: main's EXIT trap not found in $TARGET"; exit 2; }

# --- fixture: a box with skill 59 installed and its model map pinned ----------
# Two client models. Unpinned, JUDGE falls onto the HEAVY-WRITER model; the
# JUDGE pin is what keeps them independent (the live box's shape).
HW=ollama/deepseek-v4-pro:cloud
JG=ollama/mystery-x:cloud
mkdir -p "$WORK/home"
cat > "$WORK/openclaw.json" <<EOF
{"agents":{"defaults":{"model":"$HW"},"list":[]},"models":{"list":[{"id":"$JG"}]}}
EOF
mkdir -p "$WORK/tmp"
export HOME="$WORK/home" OPENCLAW_CONFIG="$WORK/openclaw.json" KIE_API_KEY=dummy-kie-not-a-real-secret
export TMPDIR="$WORK/tmp"

new_box() {  # $1 = box dir. Installs the current skill + shared-utils.
  mkdir -p "$1/skills"
  cp -R "$REPO/$SKILL" "$REPO/shared-utils" "$1/skills/"
  rm -f "$1/skills/$SKILL/model-map.json"
}
RELEASE="$WORK/release"
mkdir -p "$RELEASE"
cp -R "$REPO/$SKILL" "$RELEASE/"
rm -f "$RELEASE/$SKILL/model-map.json"

# $1 = box dir, $2 = release dir, $3 = optional replacement body for
# oc_remove_tree_guarded (simulates the guard refusing), $4 = skill name.
simulate_update() {
  # bash runs a subshell's EXIT trap with the caller's redirections already
  # undone, so the log redirect lives inside the subshell.
  ( exec >>"$WORK/sim.log" 2>&1
    set -euo pipefail
    . "${SIM_LIB:-$LIB}"
    [ -z "${3:-}" ] || eval "oc_remove_tree_guarded() { $3; }"
    if [ -n "${SIM_RM_FAIL:-}" ]; then  # the stash cannot be removed
      rm() { case "$*" in *oc-skill-box-state.*) echo "rm: $*: Operation not permitted" >&2; return 1 ;; esac; command rm "$@"; }
    fi
    UPDATE_LOCK_FD="" UPDATE_LOCK_PATH="$WORK/update.lock"
    UPDATE_LOCK_PID_FILE="$UPDATE_LOCK_PATH/pid"
    command rm -rf "$UPDATE_LOCK_PATH"; mkdir "$UPDATE_LOCK_PATH" && echo "$$" > "$UPDATE_LOCK_PID_FILE"
    eval "$TRAP_LINE"
    SKILLS_DIR="$1/skills" SKILL_DIR="$2/${4:-$SKILL}/" SKILL_NAME="${4:-$SKILL}"
    install_one_skill )
}
lock_released() { [ ! -e "$WORK/update.lock" ]; }
stash_left() { ls -d "$TMPDIR"/oc-skill-box-state.* 2>/dev/null | wc -l | tr -d ' '; }

pins_of() { python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1])).get("owner_pins"), sort_keys=True))' "$1" 2>/dev/null || echo MISSING; }
WANT_PINS="$(python3 -c 'import json,sys; print(json.dumps({"HEAVY-WRITER":sys.argv[1],"JUDGE":sys.argv[2]}, sort_keys=True))' "$HW" "$JG")"

# --- 3. control: no pins -> judge collapse fails closed ------------------------
hdr "control: the same client with NO pins fails closed"
BOX0="$WORK/box0"; new_box "$BOX0"
out="$(bash "$BOX0/skills/$SKILL/preflight.sh" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'AF-AE-JUDGE-INDEPENDENCE'; then
  ok "unpinned re-resolve fails closed on AF-AE-JUDGE-INDEPENDENCE (rc=$rc)"
else
  bad "control did not fail closed on judge independence (rc=$rc); the fixture proves nothing"
fi

# --- 1+2. pinned box survives an update and re-resolves ------------------------
hdr "owner pins survive the update and are honored by preflight"
BOX="$WORK/box1"; new_box "$BOX"
printf '{"owner_pins": %s}\n' "$WANT_PINS" > "$BOX/skills/$SKILL/model-map.json"
bash "$BOX/skills/$SKILL/preflight.sh" >/dev/null 2>&1 \
  || { echo "FATAL: could not seed a pinned map"; exit 2; }
[ "$(pins_of "$BOX/skills/$SKILL/model-map.json")" = "$WANT_PINS" ] \
  || { echo "FATAL: seeded map lost its pins before the update"; exit 2; }
echo stray > "$BOX/skills/$SKILL/stray-not-allow-listed.txt"

simulate_update "$BOX" "$RELEASE" || { cat "$WORK/sim.log"; bad "simulated update exited non-zero"; }
got="$(pins_of "$BOX/skills/$SKILL/model-map.json")"
if [ "$got" = "$WANT_PINS" ]; then
  ok "model-map.json still carries owner_pins after the update"
else
  bad "owner_pins lost by the update (got: $got)"
fi
[ "$(stash_left)" = 0 ] && ok "no stash dir left after a normal update" || bad "stash dir left after a normal update"
lock_released && ok "update lock released" || bad "update lock LEAKED"

out="$(bash "$BOX/skills/$SKILL/preflight.sh" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ]; then ok "post-update re-resolve PASSES"; else bad "post-update re-resolve failed (rc=$rc): $(printf '%s' "$out" | grep -m1 AF-AE || true)"; fi
for pin in "HEAVY-WRITER -> $HW" "JUDGE -> $JG"; do
  if printf '%s' "$out" | grep -qF "owner pin honored: $pin"; then ok "pin honored: $pin"; else bad "pin not honored: $pin"; fi
done
got="$(pins_of "$BOX/skills/$SKILL/model-map.json")"
[ "$got" = "$WANT_PINS" ] && ok "owner_pins carried forward for the next roll" || bad "owner_pins not carried forward (got: $got)"
if python3 - "$BOX/skills/$SKILL/model-map.json" 2>/dev/null <<'PY'
import json, sys
t = json.load(open(sys.argv[1]))["tiers"]
hw, jg = t["HEAVY-WRITER"]["chain"][0], t["JUDGE"]["chain"][0]
sys.exit(0 if (hw["provider"], hw["model"]) != (jg["provider"], jg["model"]) else 1)
PY
then ok "JUDGE primary independent of HEAVY-WRITER"; else bad "JUDGE collapsed onto HEAVY-WRITER"; fi

# --- 5. allow-list only ------------------------------------------------------
hdr "only allow-listed state is preserved"
[ ! -e "$BOX/skills/$SKILL/stray-not-allow-listed.txt" ] \
  && ok "non-allow-listed file removed by the wholesale replace" \
  || bad "non-allow-listed file survived the update"

# --- 4. a shipped path always wins -------------------------------------------
hdr "a path the release ships is never overwritten"
BOX2="$WORK/box2"; new_box "$BOX2"
printf '{"owner_pins": %s, "marker": "stale-box"}\n' "$WANT_PINS" > "$BOX2/skills/$SKILL/model-map.json"
RELEASE2="$WORK/release2"; mkdir -p "$RELEASE2"; cp -R "$RELEASE/$SKILL" "$RELEASE2/"
echo '{"marker": "shipped"}' > "$RELEASE2/$SKILL/model-map.json"
simulate_update "$BOX2" "$RELEASE2"
if grep -q '"shipped"' "$BOX2/skills/$SKILL/model-map.json"; then
  ok "shipped model-map.json kept; stale box copy not restored over it"
else
  bad "stale box state overwrote a shipped file"
fi

# --- 6. the stash is never orphaned when the run dies mid-step ----------------
pinned_box() {  # $1 = box dir, installed with a pinned map
  new_box "$1"
  printf '{"owner_pins": %s}\n' "$WANT_PINS" > "$1/skills/$SKILL/model-map.json"
}

hdr "guard refuses an INTACT tree (exit 1 before removing anything)"
BOX3="$WORK/box3"; pinned_box "$BOX3"; rm -rf "$TMPDIR"/oc-skill-box-state.*
simulate_update "$BOX3" "$RELEASE" 'exit 1'; rc=$?
[ "$rc" -eq 1 ] && ok "run exits 1 as the guard does" || bad "expected rc=1, got rc=$rc"
[ "$(stash_left)" = 0 ] && ok "stash removed by the EXIT trap" || bad "stash dir ORPHANED after guard refusal: $(ls -d "$TMPDIR"/oc-skill-box-state.* 2>/dev/null)"
lock_released && ok "update lock released" || bad "update lock LEAKED"
[ "$(pins_of "$BOX3/skills/$SKILL/model-map.json")" = "$WANT_PINS" ] && ok "original map untouched" || bad "original map changed"

hdr "guard refuses after a PARTIAL removal (map already deleted)"
BOX4="$WORK/box4"; pinned_box "$BOX4"; rm -rf "$TMPDIR"/oc-skill-box-state.*
simulate_update "$BOX4" "$RELEASE" 'rm -f "$1/model-map.json" "$1/SKILL.md"; exit 1'; rc=$?
[ "$rc" -eq 1 ] && ok "run exits 1 as the guard does" || bad "expected rc=1, got rc=$rc"
[ "$(stash_left)" = 0 ] && ok "stash removed by the EXIT trap" || bad "stash dir ORPHANED after partial removal"
lock_released && ok "update lock released" || bad "update lock LEAKED"
[ "$(pins_of "$BOX4/skills/$SKILL/model-map.json")" = "$WANT_PINS" ] \
  && ok "EXIT trap put the pinned map back for the next run" || bad "pins lost on partial removal"

hdr "cp -r fails under set -e after the wipe"
BOX5="$WORK/box5"; pinned_box "$BOX5"; rm -rf "$TMPDIR"/oc-skill-box-state.*
simulate_update "$BOX5" "$WORK/no-such-release"; rc=$?
[ "$rc" -eq 1 ] && ok "run exits with cp's own status (rc=$rc)" || bad "expected cp's rc=1, got rc=$rc"
lock_released && ok "update lock released" || bad "update lock LEAKED"
[ "$(stash_left)" = 0 ] && ok "stash removed by the EXIT trap" || bad "stash dir ORPHANED after failed copy"
[ "$(pins_of "$BOX5/skills/$SKILL/model-map.json")" = "$WANT_PINS" ] \
  && ok "EXIT trap put the pinned map back for the next run" || bad "pins lost on failed copy"

# --- 7. allow-listed paths with spaces ---------------------------------------
hdr "an allow-listed path with spaces survives intact"
# A copy of the extracted block plus a test-only allow-list entry. The real
# function is still the one called; this only widens what it returns for a
# fake skill, and only for this case.
SP_SKILL="98-space-test"
SP_LIB="$WORK/lib-spaces.sh"
cp "$LIB" "$SP_LIB"
cat >> "$SP_LIB" <<'EOF'
eval "_orig_$(declare -f oc_skill_box_state_paths)"
oc_skill_box_state_paths() {
  case "${1:-}" in
    98-space-test) printf '%s\n' "state dir/owner pins.json" "plain.json" ;;
    *) _orig_oc_skill_box_state_paths "$@" ;;
  esac
}
EOF
BOX6="$WORK/box6"; mkdir -p "$BOX6/skills/$SP_SKILL/state dir" "$WORK/release6/$SP_SKILL"
echo pins-with-spaces > "$BOX6/skills/$SP_SKILL/state dir/owner pins.json"
echo plain > "$BOX6/skills/$SP_SKILL/plain.json"
echo shipped > "$WORK/release6/$SP_SKILL/SKILL.md"
rm -rf "$TMPDIR"/oc-skill-box-state.*
SIM_LIB="$SP_LIB" simulate_update "$BOX6" "$WORK/release6" "" "$SP_SKILL" || bad "space-path update exited non-zero: $(cat "$WORK/sim.log")"
[ "$(cat "$BOX6/skills/$SP_SKILL/state dir/owner pins.json" 2>/dev/null)" = pins-with-spaces ] \
  && ok "file under 'state dir/owner pins.json' preserved" || bad "path with spaces lost or split"
[ "$(cat "$BOX6/skills/$SP_SKILL/plain.json" 2>/dev/null)" = plain ] && ok "second entry preserved" || bad "second entry lost"
[ ! -e "$BOX6/skills/$SP_SKILL/state" ] && [ ! -e "$BOX6/skills/$SP_SKILL/dir" ] \
  && ok "no word-split fragments created" || bad "word-split fragments created"
[ "$(stash_left)" = 0 ] && ok "no stash dir left" || bad "stash dir left"

# --- 8. a failing stash cleanup never costs the lock or the exit status -------
stash_cleanup_case() {  # $1 = label, $2 = box, $3 = remover body, $4 = expected rc
  hdr "stash rm -rf FAILS ($1)"
  pinned_box "$2"; rm -rf "$TMPDIR"/oc-skill-box-state.* "$WORK/update.lock"; : > "$WORK/sim.log"
  SIM_RM_FAIL=1 simulate_update "$2" "$RELEASE" "$3"; rc=$?
  [ "$rc" -eq "$4" ] && ok "exit status is the script's own (rc=$rc)" || bad "exit status changed: expected $4, got $rc"
  lock_released && ok "release_update_lock ran: lock released" || bad "update lock LEAKED: every later run would refuse with LOCK HELD"
  _left="$(ls -d "$TMPDIR"/oc-skill-box-state.* 2>/dev/null | head -1)"
  if [ -n "$_left" ] && grep -qF "stash cleanup failed, left at $_left" "$WORK/sim.log"; then
    ok "log names the stash left behind"
  else
    bad "no log line naming the stash (left: ${_left:-none}): $(tail -3 "$WORK/sim.log")"
  fi
  [ "$(pins_of "$2/skills/$SKILL/model-map.json")" = "$WANT_PINS" ] && ok "pins still in place" || bad "pins lost"
  rm -rf "$TMPDIR"/oc-skill-box-state.*
}
stash_cleanup_case "exit path: guard refuses" "$WORK/box7" 'exit 1' 1
stash_cleanup_case "exit path: partial removal" "$WORK/box8" 'rm -f "$1/model-map.json"; exit 1' 1
stash_cleanup_case "normal path" "$WORK/box9" '' 0

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

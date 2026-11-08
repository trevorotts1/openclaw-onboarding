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
#   9. EXCEPTION to 4 (the 2026-10 field-map wound): 59's
#      config/field-map.json is stamped IN PLACE by the provisioner
#      (anthology_registry.py provision-fields writes field_key / field_id /
#      verified_at / location_masked) while the repo ships the pristine
#      template. A STAMPED box copy survives the update BYTE-IDENTICAL
#      (oc_skill_box_state_overrides_shipped puts it back over the shipped
#      template), and template-state boxes are unaffected: a fresh box gets
#      the shipped template, an already-template box keeps valid template
#      state. Every other path keeps contract 4.
#  10. THE CONTENT GATE MUST AGREE WITH 9. Putting the stamped copy back over
#      the shipped template made DEST bytes differ from SRC bytes on every
#      provisioned box, so the A2.5 early content-gate aborted the roll before
#      any sentinel was written (live roll fleet-roll-20261014-063709:
#        59-anthology-engine: expected=5510a154... found=4c570d46...
#        A2.5 EARLY CONTENT-GATE FAILED ... No version stamp has been written.).
#      scripts/skill-content-hash.sh therefore waives a field-map.json that is
#      in one of skill 59's TWO LEGAL states -- shipped TEMPLATE, or fully
#      STAMPED -- and only those. A HALF-stamp, a drifted field_key, a blank
#      field_id, a row count that drifted from provisioning.total_keys or
#      unparseable JSON stays IN SCOPE and still fails the gate, so the waiver
#      costs no discrimination. Proven three ways: stamped PASSES, template
#      PASSES, each corruption FAILS, and the pre-fix hasher (the field-map
#      arm neutralised) reproduces the live MISMATCH on the very same tree.
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
  # rc6 (shared installation lease): release_update_lock reads the lease state and
  # judges ownership through the _ulock_* readers, so those are extracted verbatim
  # too (state variables up to, not including, the helper loader).
  awk '/^_ulock_impl=""/{on=1} /^# Prefer the shared helper when the box has it/{on=0} on{print}' "$TARGET"
  awk '/^release_update_lock\(\) *\{/,/^}/' "$TARGET"
  awk '/^oc_update_exit_trap\(\) *\{/,/^}/' "$TARGET"
  # The helpers exist only after the fix; absent on the old updater, which is
  # fine because its install step never calls them.
  awk '/^# >>> SKILL-BOX-STATE-BEGIN/{on=1} on{print} /^# <<< SKILL-BOX-STATE-END/{on=0}' "$TARGET"
  echo 'install_one_skill() {'
  awk '/^    # Remove old version if exists\./{on=1} on{print} on && /echo "    Updated: \$SKILL_NAME"/{exit}' "$TARGET"
  echo '}'
} > "$LIB"
grep -q 'cp -R "${SKILL_DIR%/}" "$SKILLS_DIR/"' "$LIB" \
  || { echo "FATAL: install-loop anchors drifted; nothing extracted from $TARGET"; exit 2; }
bash -n "$LIB" || { echo "FATAL: extracted block does not parse"; exit 2; }
# main's EXIT trap, verbatim (the only `trap ... EXIT` in main).
TRAP_LINE="$(awk '/^main\(\) *\{/{on=1} on && /^  trap .* EXIT$/{print; exit}' "$TARGET")"
[ -n "$TRAP_LINE" ] || { echo "FATAL: main's EXIT trap not found in $TARGET"; exit 2; }

# --- fixture: a box with skill 59 installed and its model map pinned ----------
# Two client models. Unpinned, JUDGE falls onto the HEAVY-WRITER model; the
# JUDGE pin is what keeps them independent (the live box's shape).
HW=ollama/deepseek-v4.1-flash:cloud
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
    # The run owns this (legacy mkdir) lease; the real acquire sets the same state.
    _ulock_impl="inline"; _ulock_state="owned"
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

# --- 9. the field-map exception (the 2026-10 every-roll wipe) -----------------
# The provisioner stamps 59's config/field-map.json IN PLACE (38 rows:
# field_key, field_id, verified_at, location_masked -> values) while the repo
# ships the pristine template (all four null). Before the fix every roll
# re-templated the stamped copy and verify-fields exited 1 until re-stamped.
FM_REL="config/field-map.json"
stamp_field_map() {  # $1 = a field-map.json path; stamps it like the provisioner
  python3 - "$1" <<'PY'
import json, sys
p = sys.argv[1]
fm = json.load(open(p))
for i, item in enumerate(fm["provisioning"]["fields"]):
    item["field_key"] = item["intended_key"]
    item["field_id"] = 90000 + i
    item["verified_at"] = "2026-10-14T00:00:00Z"
    item["location_masked"] = "••••4242"
with open(p, "w") as fh:
    json.dump(fm, fh, indent=2, sort_keys=True)
PY
}

hdr "a STAMPED field-map.json survives the update byte-identical"
BOXF="$WORK/boxf"; new_box "$BOXF"
stamp_field_map "$BOXF/skills/$SKILL/$FM_REL"
cp "$BOXF/skills/$SKILL/$FM_REL" "$WORK/field-map-stamped-want"
rm -rf "$TMPDIR"/oc-skill-box-state.*
simulate_update "$BOXF" "$RELEASE"
if cmp -s "$WORK/field-map-stamped-want" "$BOXF/skills/$SKILL/$FM_REL"; then
  ok "stamped field-map survived the copy pass byte-identical"
else
  bad "stamped field-map was re-templated by the update"
fi
if cmp -s "$RELEASE/$SKILL/$FM_REL" "$BOXF/skills/$SKILL/$FM_REL"; then
  bad "field-map equals the shipped pristine template -- the stamp was wiped"
else
  ok "field-map is the stamped box copy, not the shipped template"
fi
python3 - "$BOXF/skills/$SKILL/$FM_REL" <<'PY' \
  && ok "all 38 rows still carry field_key/field_id/verified_at/location_masked" \
  || bad "a stamped row lost its stamps"
import json, sys
rows = json.load(open(sys.argv[1]))["provisioning"]["fields"]
assert len(rows) == 38, len(rows)
for r in rows:
    assert r["field_key"] and r["field_id"] and r["verified_at"] and r["location_masked"], r
PY
grep -qF "box state preserved over the shipped template: $SKILL/$FM_REL" "$WORK/sim.log" \
  && ok "log names the override restore" || bad "no override-restore log line: $(tail -3 "$WORK/sim.log")"
[ "$(stash_left)" = 0 ] && ok "no stash dir left after the field-map update" || bad "stash dir left"

hdr "template-state field-map stays legal (fresh box and already-template box)"
# Fresh box: no field-map on the box at all -- the shipped template simply lands.
BOXG="$WORK/boxg"; new_box "$BOXG"; rm -f "$BOXG/skills/$SKILL/$FM_REL"
rm -rf "$TMPDIR"/oc-skill-box-state.*
simulate_update "$BOXG" "$RELEASE"
cmp -s "$RELEASE/$SKILL/$FM_REL" "$BOXG/skills/$SKILL/$FM_REL" \
  && ok "fresh box: shipped template installed unchanged" \
  || bad "fresh box: shipped template did not land"
# Already-template box: the update stays clean and the file stays template
# state (all stamps null), exactly as before this fix.
BOXH="$WORK/boxh"; new_box "$BOXH"
rm -rf "$TMPDIR"/oc-skill-box-state.*
simulate_update "$BOXH" "$RELEASE" || bad "template-state box update exited non-zero: $(tail -3 "$WORK/sim.log")"
python3 - "$BOXH/skills/$SKILL/$FM_REL" <<'PY' \
  && ok "template-state box: valid JSON, every stamp still null" \
  || bad "template-state box: file is not template-state valid"
import json, sys
rows = json.load(open(sys.argv[1]))["provisioning"]["fields"]
assert all(r["field_key"] is None and r["field_id"] is None for r in rows), "unexpected stamp on a template-state box"
PY
[ "$(stash_left)" = 0 ] && ok "no stash dir left (template-state box)" || bad "stash dir left (template-state box)"

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

# --- 10. the content gate agrees with the preservation contract ---------------
# SRC is what the release ships (EXTRACTED_DIR); DEST is the box's skills dir
# after the simulated update above, i.e. the release copy PLUS the preserved
# box state. Same two trees the updater feeds to scripts/skill-content-hash.sh
# for A2.5 and A3 -- that helper is the ONLY hasher in the updater (A2.5, A3
# and the same-version content recheck all shell out to it, as do
# scripts/verify-skills-complete.sh and 60-zhc's ews_baseline.py).
HASH_TOOL="$REPO/scripts/skill-content-hash.sh"
[ -f "$HASH_TOOL" ] || { echo "FATAL: $HASH_TOOL not found"; exit 2; }
gt_src_root() { rm -rf "$1"; mkdir -p "$1"; cp -R "$RELEASE/$SKILL" "$1/"; }
digest_of() { bash "$HASH_TOOL" "$1" 2>/dev/null | awk -F'|' -v n="$2" '$1==n {print $2; exit}'; }

corrupt_field_map() {  # $1 = case, $2 = path. Leaves the file in a state that
                       # is neither the template nor a complete stamp.
  python3 - "$1" "$2" <<'PY'
import json, sys
case, p = sys.argv[1], sys.argv[2]
if case == "garbage":
    open(p, "w").write("{ this is not json")
    sys.exit(0)
fm = json.load(open(p))
rows = fm["provisioning"]["fields"]
if case == "half-stamp":          # field_key stamped, field_id left null
    rows[3]["field_id"] = None
elif case == "row-deleted":       # count drifts from provisioning.total_keys
    rows.pop()
elif case == "drifted-key":       # stamped, but the key no longer equals intended_key
    for i, r in enumerate(rows):
        r["field_key"], r["field_id"] = "contact.wrong_key_%d" % i, "fid%d" % i
elif case == "blank-field-id":    # stamped, but every field_id is blank
    for r in rows:
        r["field_key"], r["field_id"] = r["intended_key"], ""
else:
    raise SystemExit("unknown corruption case: %s" % case)
json.dump(fm, open(p, "w"), indent=2, sort_keys=True)
PY
}

GT_SRC="$WORK/gt-src"; gt_src_root "$GT_SRC"
SRC_D="$(digest_of "$GT_SRC" "$SKILL")"
[ -n "$SRC_D" ] || { echo "FATAL: skill-content-hash.sh produced no digest for $SKILL"; exit 2; }

hdr "content gate: the preserved STAMPED field-map PASSES"
D="$(digest_of "$BOXF/skills" "$SKILL")"
if [ "$D" = "$SRC_D" ]; then
  ok "stamped + preserved-over-shipped DEST digest == SRC digest (A2.5 passes)"
else
  bad "stamped field-map still fails the content gate: expected=$SRC_D found=$D"
fi

hdr "content gate: template-state boxes PASS"
D="$(digest_of "$BOXH/skills" "$SKILL")"
[ "$D" = "$SRC_D" ] && ok "already-template box digest == SRC digest" \
                    || bad "template-state box fails the gate: expected=$SRC_D found=$D"
D="$(digest_of "$BOXG/skills" "$SKILL")"
[ "$D" = "$SRC_D" ] && ok "fresh box digest == SRC digest" \
                    || bad "fresh box fails the gate: expected=$SRC_D found=$D"

hdr "content gate: a genuinely corrupted preserved file still FAILS"
FM_BOX="$BOXF/skills/$SKILL/$FM_REL"
for _case in half-stamp row-deleted garbage drifted-key blank-field-id; do
  corrupt_field_map "$_case" "$FM_BOX"
  D="$(digest_of "$BOXF/skills" "$SKILL")"
  if [ -n "$D" ] && [ "$D" != "$SRC_D" ]; then
    ok "$_case: gate FAILS (discrimination kept)"
  else
    bad "$_case: gate PASSED on a corrupted preserved field-map"
  fi
  cp -p "$WORK/field-map-stamped-want" "$FM_BOX"   # put the legal stamp back
done
D="$(digest_of "$BOXF/skills" "$SKILL")"
[ "$D" = "$SRC_D" ] && ok "restored stamped map passes again (the failures were the corruptions)" \
                    || bad "restored stamped map no longer passes: expected=$SRC_D found=$D"

hdr "control: the pre-fix hasher reproduces the live A2.5 failure"
# Neutralise ONLY the field-map arm -- the pattern can never match, so the
# file stays in scope exactly as it did before the fix. Everything else in the
# helper is byte-identical, so this is the pre-fix instrument, not a rewrite.
PREFIX_HASH="$WORK/skill-content-hash-prefix.sh"
python3 - "$HASH_TOOL" "$PREFIX_HASH" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()
needle = "    field-map.json)\n"
assert t.count(needle) == 1, "field-map arm not found exactly once"
open(dst, "w").write(t.replace(needle, "    no-exclude-field-map.json)\n"))
PY
bash -n "$PREFIX_HASH" || { echo "FATAL: control hasher does not parse"; exit 2; }
cp -p "$WORK/field-map-stamped-want" "$FM_BOX"
D="$(bash "$PREFIX_HASH" "$BOXF/skills" 2>/dev/null | awk -F'|' -v n="$SKILL" '$1==n {print $2; exit}')"
if [ -n "$D" ] && [ "$D" != "$SRC_D" ]; then
  ok "pre-fix control: expected=$SRC_D found=$D -> A2.5 would abort, stamp withheld"
else
  bad "pre-fix control did NOT reproduce the live mismatch (got: ${D:-<empty>})"
fi
D="$(bash "$PREFIX_HASH" "$GT_SRC" 2>/dev/null | awk -F'|' -v n="$SKILL" '$1==n {print $2; exit}')"
D_T="$(bash "$PREFIX_HASH" "$BOXH/skills" 2>/dev/null | awk -F'|' -v n="$SKILL" '$1==n {print $2; exit}')"
if [ -n "$D" ] && [ "$D" = "$D_T" ]; then
  ok "control instrument is sound: pre-fix hasher agrees with itself on a template-state box"
else
  bad "control instrument broken (src=${D:-<empty>} template=${D_T:-<empty>}) — the mismatch above would prove nothing"
fi

hdr "control: the hasher can fail at all (a non-excluded file)"
CTL_FILE="$(find "$BOXF/skills/$SKILL" -maxdepth 1 -type f -name '*.md' 2>/dev/null | LC_ALL=C sort | head -1)"
[ -n "$CTL_FILE" ] || { echo "FATAL: no top-level .md in $SKILL to use as a control"; exit 2; }
printf '\ncontrol-corruption\n' >> "$CTL_FILE"
D="$(digest_of "$BOXF/skills" "$SKILL")"
if [ -n "$D" ] && [ "$D" != "$SRC_D" ]; then
  ok "corrupting a non-excluded shipped file fails the gate"
else
  bad "corrupting a non-excluded shipped file did NOT fail the gate (got: ${D:-<empty>})"
fi
cp -p "$GT_SRC/$SKILL/$(basename "$CTL_FILE")" "$CTL_FILE"
D="$(digest_of "$BOXF/skills" "$SKILL")"
[ "$D" = "$SRC_D" ] && ok "control file restored, gate passes again" \
                    || bad "control file restore failed: expected=$SRC_D found=$D"

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

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
#
# METHOD. The wipe+copy step is EXTRACTED VERBATIM from the updater's skill
# install loop (between the "# Remove old version if exists." anchor and the
# "Updated: $SKILL_NAME" echo, both present since before the fix), so running
# this suite with UPDATER_UNDER_TEST=<old update-skills.sh> reproduces the
# defect. oc_remove_tree_guarded is stubbed to a plain rm -rf: its own guard
# has its own suite, this one tests what survives the replace.
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

# --- fixture: a box with skill 59 installed and its model map pinned ----------
# Two client models. Unpinned, JUDGE falls onto the HEAVY-WRITER model; the
# JUDGE pin is what keeps them independent (the live box's shape).
HW=ollama/deepseek-v4-pro:cloud
JG=ollama/mystery-x:cloud
mkdir -p "$WORK/home"
cat > "$WORK/openclaw.json" <<EOF
{"agents":{"defaults":{"model":"$HW"},"list":[]},"models":{"list":[{"id":"$JG"}]}}
EOF
export HOME="$WORK/home" OPENCLAW_CONFIG="$WORK/openclaw.json" KIE_API_KEY=dummy-kie-not-a-real-secret

new_box() {  # $1 = box dir. Installs the current skill + shared-utils.
  mkdir -p "$1/skills"
  cp -R "$REPO/$SKILL" "$REPO/shared-utils" "$1/skills/"
  rm -f "$1/skills/$SKILL/model-map.json"
}
RELEASE="$WORK/release"
mkdir -p "$RELEASE"
cp -R "$REPO/$SKILL" "$RELEASE/"
rm -f "$RELEASE/$SKILL/model-map.json"

simulate_update() {  # $1 = box dir, $2 = release dir
  ( set -euo pipefail
    . "$LIB"
    SKILLS_DIR="$1/skills" SKILL_DIR="$2/$SKILL/" SKILL_NAME="$SKILL"
    install_one_skill )
}

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

simulate_update "$BOX" "$RELEASE" >"$WORK/update.log" 2>&1 || { cat "$WORK/update.log"; bad "simulated update exited non-zero"; }
got="$(pins_of "$BOX/skills/$SKILL/model-map.json")"
if [ "$got" = "$WANT_PINS" ]; then
  ok "model-map.json still carries owner_pins after the update"
else
  bad "owner_pins lost by the update (got: $got)"
fi

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
simulate_update "$BOX2" "$RELEASE2" >/dev/null 2>&1
if grep -q '"shipped"' "$BOX2/skills/$SKILL/model-map.json"; then
  ok "shipped model-map.json kept; stale box copy not restored over it"
else
  bad "stale box state overwrote a shipped file"
fi

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

#!/usr/bin/env bash
# ============================================================================
# updater-preserves-skill75-interrupt-state.test.sh
#
# THE DEFECT THIS LOCKS
# update-skills.sh replaces every numbered skill WHOLESALE: a guarded remove,
# then `cp -R` from the release. An interrupted Skill 75 run keeps its resume
# state INSIDE the installed skill folder:
#   .checkpoint-pending                     (skill root -- the pending marker)
#   scripts/core/state_store.py.part        (half-written canonical module)
# Neither path is shipped by the release, so the remove+copy destroyed both and
# an interrupted run could not resume across an update. The acceptance harness
# tests/w10-canary/upgrade_canary.py seeds exactly these two paths and asserts
# they survive the upgrade ("interrupted-run state preserved").
#
# THE CONTRACT UNDER TEST
#   (a) Skill 75's .checkpoint-pending and scripts/core/state_store.py.part
#       survive an update BYTE-IDENTICAL.
#   (b) SCOPED: the same two relative paths in an UNRELATED skill's tree are
#       still removed by the wholesale replace.
#   (c) REGRESSION: 59-anthology-engine's two allow-listed entries still
#       survive (model-map.json and the stamped config/field-map.json).
#   (d) RESUME: after the upgrade the marker is still readable and carries the
#       saved stage, so the resume path can find its checkpoint.
#   (e) The A2.5/A3 content gate still PASSES for Skill 75 with the preserved
#       files present -- otherwise the roll aborts at the copy site and the
#       version stamp is withheld. scripts/skill-content-hash.sh must exclude
#       the same two relative paths, scoped to this skill.
#
# NEGATIVE CONTROLS (so the test cannot pass for the wrong reason)
#   - The PRE-FIX allow-list (no 75 branch) reproduces the LOSS.
#   - The PRE-FIX hasher (75 exclusions neutralised) reproduces the gate
#     MISMATCH on the very same tree.
#   - An unrelated skill's .part is NOT excluded from the hasher, so the
#     exclusion cannot have been made by basename.
#
# METHOD. The wipe+copy step and the SKILL-BOX-STATE block are EXTRACTED
# VERBATIM from update-skills.sh (same anchors as
# updater-preserves-skill-box-state.test.sh), so this exercises the real
# mechanism, not a copy of it. oc_remove_tree_guarded is stubbed to a plain
# rm -rf: its own guard has its own suite; this one tests what SURVIVES the
# replace.
#
# SAFETY. Everything runs inside mktemp -d with HOME pointed there. No network,
# no box, no secrets.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
TARGET="${UPDATER_UNDER_TEST:-$REPO/update-skills.sh}"
S75=75-drama-song-ad-factory
S59=59-anthology-engine
SOTHER=46-kie-callback-relay

PASS=0; FAIL=0
ok()  { printf '  PASS: %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n== %s ==\n' "$1"; }

[ -f "$TARGET" ] || { echo "FATAL: $TARGET not found"; exit 2; }
HASH_TOOL="$REPO/scripts/skill-content-hash.sh"
[ -f "$HASH_TOOL" ] || { echo "FATAL: $HASH_TOOL not found"; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- verbatim extraction ------------------------------------------------------
LIB="$WORK/lib.sh"
{
  echo 'oc_remove_tree_guarded() { rm -rf "$1"; }'
  awk '/^# >>> SKILL-BOX-STATE-BEGIN/{on=1} on{print} /^# <<< SKILL-BOX-STATE-END/{on=0}' "$TARGET"
  echo 'install_one_skill() {'
  awk '/^    # Remove old version if exists\./{on=1} on{print} on && /echo "    Updated: \$SKILL_NAME"/{exit}' "$TARGET"
  echo '}'
} > "$LIB"
grep -q 'cp -R "${SKILL_DIR%/}" "$SKILLS_DIR/"' "$LIB" \
  || { echo "FATAL: install-loop anchors drifted; nothing extracted from $TARGET"; exit 2; }
grep -q 'oc_skill_box_state_restore "$SKILL_NAME"' "$LIB" \
  || { echo "FATAL: box-state restore not extracted; the block anchor drifted"; exit 2; }
bash -n "$LIB" || { echo "FATAL: extracted block does not parse"; exit 2; }

export HOME="$WORK/home"; export TMPDIR="$WORK/tmp"
mkdir -p "$HOME" "$TMPDIR"

# --- fixture ------------------------------------------------------------------
# A box installed at the PRIOR revision: skill trees copied from this checkout,
# with the release shipping the same content so "survived" cannot be confused
# with "the release happens to ship it".
RELEASE="$WORK/release"
mkdir -p "$RELEASE"
for s in "$S75" "$S59" "$SOTHER"; do cp -R "$REPO/$s" "$RELEASE/"; done

new_box() {  # $1 = box dir
  mkdir -p "$1/skills"
  for s in "$S75" "$S59" "$SOTHER"; do cp -R "$RELEASE/$s" "$1/skills/"; done
  rm -rf "$1/skills/$S75/scripts/core/state_store.py.part" \
         "$1/skills/$S75/.checkpoint-pending"
}

simulate_update() {  # $1 = box dir, $2 = skill name, $3 = optional lib override
  ( exec >>"$WORK/sim-$2.log" 2>&1
    set -euo pipefail
    . "${3:-$LIB}"
    SKILLS_DIR="$1/skills" SKILL_DIR="$RELEASE/$2/" SKILL_NAME="$2"
    LOG_FILE="$WORK/sim-$2.log"
    install_one_skill )
}

# --- (a) Skill 75 interrupt state survives ------------------------------------
hdr "Skill 75 interrupted-run state survives the wholesale replace"
BOX="$WORK/box"; new_box "$BOX"
MARK_REL=".checkpoint-pending"
PART_REL="scripts/core/state_store.py.part"
printf 'resume-stage:music\n' > "$BOX/skills/$S75/$MARK_REL"
mkdir -p "$BOX/skills/$S75/$(dirname "$PART_REL")"
printf 'partial' > "$BOX/skills/$S75/$PART_REL"
echo stray > "$BOX/skills/$S75/stray-not-allow-listed.txt"
cp "$BOX/skills/$S75/$MARK_REL" "$WORK/want-marker"
cp "$BOX/skills/$S75/$PART_REL" "$WORK/want-part"

simulate_update "$BOX" "$S75" || bad "simulated 75 update exited non-zero: $(tail -3 "$WORK/sim-$S75.log")"
if [ -f "$BOX/skills/$S75/$MARK_REL" ]; then
  ok ".checkpoint-pending survived the update"
else
  bad ".checkpoint-pending DESTROYED by the update"
fi
if [ -f "$BOX/skills/$S75/$PART_REL" ]; then
  ok "scripts/core/state_store.py.part survived the update"
else
  bad "scripts/core/state_store.py.part DESTROYED by the update"
fi
cmp -s "$WORK/want-marker" "$BOX/skills/$S75/$MARK_REL" \
  && ok "marker is byte-identical (not re-created empty)" || bad "marker bytes changed"
cmp -s "$WORK/want-part" "$BOX/skills/$S75/$PART_REL" \
  && ok ".part is byte-identical" || bad ".part bytes changed"
# SCOPING, inside the SAME skill that now has an allow-list: preservation must
# never become blanket. Anything not on the list is still wiped by the replace.
[ ! -e "$BOX/skills/$S75/stray-not-allow-listed.txt" ] \
  && ok "Skill 75: non-allow-listed file still removed (preservation is not blanket)" \
  || bad "Skill 75: non-allow-listed file SURVIVED -- preservation went blanket"

# --- (d) resume can still find its checkpoint --------------------------------
hdr "an interrupted run can still find its checkpoint after the upgrade"
if [ -f "$BOX/skills/$S75/$MARK_REL" ]; then
  stage="$(sed -n 's/^resume-stage://p' "$BOX/skills/$S75/$MARK_REL" 2>/dev/null)"
  [ "$stage" = "music" ] \
    && ok "checkpoint still parses to the saved stage (resume-stage:music)" \
    || bad "checkpoint unreadable or stage lost (got: '${stage}')"
else
  bad "no checkpoint on disk -- the run would restart from intake"
fi

# --- (b) scoped: unrelated skill loses the same files ------------------------
hdr "SCOPED: the same paths in an unrelated skill are still removed"
BOX2="$WORK/box2"; new_box "$BOX2"
printf 'resume-stage:music\n' > "$BOX2/skills/$SOTHER/$MARK_REL"
mkdir -p "$BOX2/skills/$SOTHER/$(dirname "$PART_REL")"
printf 'partial' > "$BOX2/skills/$SOTHER/$PART_REL"
simulate_update "$BOX2" "$SOTHER" || bad "simulated other-skill update exited non-zero"
[ ! -e "$BOX2/skills/$SOTHER/$MARK_REL" ] \
  && ok "unrelated skill: .checkpoint-pending removed (not preserved)" \
  || bad "unrelated skill: .checkpoint-pending WRONGLY preserved"
[ ! -e "$BOX2/skills/$SOTHER/$PART_REL" ] \
  && ok "unrelated skill: state_store.py.part removed (not preserved)" \
  || bad "unrelated skill: state_store.py.part WRONGLY preserved"

# --- (c) 59's two entries still survive -------------------------------------
hdr "REGRESSION: 59-anthology-engine's allow-listed state still survives"
BOX3="$WORK/box3"; new_box "$BOX3"
printf '{"owner_pins": {"JUDGE": "keep-me"}}\n' > "$BOX3/skills/$S59/model-map.json"
cp "$BOX3/skills/$S59/model-map.json" "$WORK/want59-map"
printf '{"stamped": true}\n' > "$BOX3/skills/$S59/config/field-map.json"
cp "$BOX3/skills/$S59/config/field-map.json" "$WORK/want59-fm"
simulate_update "$BOX3" "$S59" || bad "simulated 59 update exited non-zero"
cmp -s "$WORK/want59-map" "$BOX3/skills/$S59/model-map.json" \
  && ok "59 model-map.json still carries owner_pins" || bad "59 model-map.json lost/changed"
cmp -s "$WORK/want59-fm" "$BOX3/skills/$S59/config/field-map.json" \
  && ok "59 config/field-map.json still stamped byte-identical" || bad "59 field-map lost/changed"

# --- (e) the A2.5/A3 content gate still passes ------------------------------
hdr "A2.5/A3 content gate still passes for Skill 75 with the state present"
digest_of() { bash "$HASH_TOOL" "$1" 2>/dev/null | awk -F'|' -v n="$2" '$1==n {print $2; exit}'; }
SRC_ROOT="$WORK/src-root"; rm -rf "$SRC_ROOT"; mkdir -p "$SRC_ROOT"
cp -R "$RELEASE/$S75" "$SRC_ROOT/"
SRC_D="$(digest_of "$SRC_ROOT" "$S75")"
[ -n "$SRC_D" ] || { echo "FATAL: skill-content-hash.sh produced no digest for $S75"; exit 2; }
BOX_D="$(digest_of "$BOX/skills" "$S75")"
[ "$BOX_D" = "$SRC_D" ] \
  && ok "DEST digest == SRC digest (version stamp not withheld)" \
  || bad "content gate would ABORT the roll: expected=$SRC_D found=$BOX_D"

hdr "control: the hasher can still fail at all on Skill 75"
CTL_FILE="$BOX/skills/$S75/SKILL.md"
cp -p "$CTL_FILE" "$WORK/skill-md-backup"
printf '\ncontrol-corruption\n' >> "$CTL_FILE"
BOX_D="$(digest_of "$BOX/skills" "$S75")"
[ -n "$BOX_D" ] && [ "$BOX_D" != "$SRC_D" ] \
  && ok "corrupting a shipped Skill 75 file still fails the gate" \
  || bad "hasher no longer detects corruption in Skill 75"
cp -p "$WORK/skill-md-backup" "$CTL_FILE"
BOX_D="$(digest_of "$BOX/skills" "$S75")"
[ "$BOX_D" = "$SRC_D" ] && ok "restored file passes again" \
  || bad "restore failed: expected=$SRC_D found=$BOX_D"

hdr "control: an unrelated skill's .part is still hashed (exclusion is not basename-wide)"
mkdir -p "$SRC_ROOT/$SOTHER"
cp -R "$RELEASE/$SOTHER" "$SRC_ROOT/"
OTHER_SRC="$(digest_of "$SRC_ROOT" "$SOTHER")"
mkdir -p "$BOX2/skills/$SOTHER/scripts/core"
printf 'partial' > "$BOX2/skills/$SOTHER/scripts/core/state_store.py.part"
OTHER_BOX="$(digest_of "$BOX2/skills" "$SOTHER")"
[ -n "$OTHER_SRC" ] && [ "$OTHER_BOX" != "$OTHER_SRC" ] \
  && ok "unrelated skill's .part changes its digest (still in scope)" \
  || bad "unrelated skill's .part was excluded -- exclusion leaked by basename"

# --- negative control: the PRE-FIX allow-list reproduces the loss ------------
hdr "control (pre-fix): without the 75 branch the state IS destroyed"
PREFIX_LIB="$WORK/lib-prefix.sh"
cp "$LIB" "$PREFIX_LIB"
cat >> "$PREFIX_LIB" <<'EOF'
eval "_orig_$(declare -f oc_skill_box_state_paths)"
oc_skill_box_state_paths() {
  case "${1:-}" in
    75-drama-song-ad-factory) return 0 ;;
    *) _orig_oc_skill_box_state_paths "$@" ;;
  esac
}
EOF
bash -n "$PREFIX_LIB" || { echo "FATAL: pre-fix control lib does not parse"; exit 2; }
BOX4="$WORK/box4"; new_box "$BOX4"
printf 'resume-stage:music\n' > "$BOX4/skills/$S75/$MARK_REL"
mkdir -p "$BOX4/skills/$S75/$(dirname "$PART_REL")"
printf 'partial' > "$BOX4/skills/$S75/$PART_REL"
simulate_update "$BOX4" "$S75" "$PREFIX_LIB" || bad "pre-fix control update exited non-zero"
[ ! -e "$BOX4/skills/$S75/$MARK_REL" ] && [ ! -e "$BOX4/skills/$S75/$PART_REL" ] \
  && ok "pre-fix control: both files LOST (the defect reproduces)" \
  || bad "pre-fix control did not reproduce the loss -- the positive case proves nothing"

# --- negative control: the hasher exclusion is load-bearing ------------------
hdr "control (pre-fix): neutralising the 75 hasher arms reproduces the mismatch"
PREFIX_HASH="$WORK/skill-content-hash-prefix.sh"
python3 - "$HASH_TOOL" "$PREFIX_HASH" <<'PY'
import sys
src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()
needle = "    */75-drama-song-ad-factory/.checkpoint-pending) return 0 ;;\n"
assert t.count(needle) == 1, "75 marker arm not found exactly once"
t = t.replace(needle, "    no-exclude-75-marker) return 0 ;;\n")
open(dst, "w").write(t)
PY
bash -n "$PREFIX_HASH" || { echo "FATAL: pre-fix hasher control does not parse"; exit 2; }
PREFIX_D="$(bash "$PREFIX_HASH" "$BOX/skills" 2>/dev/null | awk -F'|' -v n="$S75" '$1==n {print $2; exit}')"
if [ -n "$PREFIX_D" ] && [ "$PREFIX_D" != "$SRC_D" ]; then
  ok "pre-fix hasher: expected=$SRC_D found=$PREFIX_D -> A2.5 would abort, stamp withheld"
else
  bad "pre-fix hasher control did NOT reproduce the mismatch (got: ${PREFIX_D:-<empty>})"
fi

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

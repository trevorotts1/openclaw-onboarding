#!/usr/bin/env bash
# Retired "NN-name-ARCHIVED" skills: the repo ships none, and every roll moves them off a box.
#
# Why this exists. OpenClaw rescans the skills folder constantly and logs one error per scan for
# every folder it cannot load (234 times per folder in 13 hours on a real client box), so a retired
# skill folder inside a box's skills folder is noise forever. Three halves are locked here:
#   (1) repo level   - no *-ARCHIVED folder at the repository root, so none can reach a box again;
#   (2) box level    - scripts/remove-archived-skills.sh MOVES exactly the ^[0-9]+-.*-ARCHIVED$
#                      directories out of a skills folder into <parent>/retired-skills/ (the same
#                      destination and naming update-skills.sh uses for a retired live copy), never
#                      deleting content and never overwriting an earlier retired copy; a second run
#                      is a silent no-op;
#   (3) wiring       - update-skills.sh and install.sh call it, update-skills.sh before the content
#                      recheck early exit and outside the per-version .wired-<version> sentinel.
# Hermetic: only a mktemp fixture is touched, never a real ~/.openclaw.
#
# Override hooks, used only to prove this test can fail (see the PR notes):
#   REMOVE_ARCHIVED_SCRIPT=<path to a mutated copy of the script>
#   ARCHIVED_TEST_REPO=<path to a repo tree to inspect instead of this checkout>
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="${REMOVE_ARCHIVED_SCRIPT:-$REPO/scripts/remove-archived-skills.sh}"
TREE="${ARCHIVED_TEST_REPO:-$REPO}"
T="$(mktemp -d)"; trap 'chmod -R u+rwx "$T" 2>/dev/null; rm -rf "$T"' EXIT
fail=0; ok(){ echo "PASS $1"; }; bad(){ echo "FAIL $1"; fail=1; }

# ---- (1) repo level: nothing named *-ARCHIVED ships ------------------------------------------
shipped="$(find "$TREE" -maxdepth 1 -mindepth 1 -type d -name '*-ARCHIVED' -not -path '*/.git/*' 2>/dev/null | sed 's|.*/||' | sort | tr '\n' ' ')"
[ -z "$shipped" ] && ok "repo ships no *-ARCHIVED folder" || bad "repo ships retired folder(s): $shipped"
tracked="$(git -C "$TREE" ls-files 2>/dev/null | grep -E '^[0-9]+-[^/]*-ARCHIVED/' | head -3 | tr '\n' ' ')"
[ -z "$tracked" ] && ok "git tracks no file under a *-ARCHIVED folder" || bad "git tracks: $tracked"

# ---- (2) box level: fixture skills folder ----------------------------------------------------
[ -f "$SCRIPT" ] || { bad "remove-archived-skills.sh missing at $SCRIPT"; exit 1; }
bash -n "$SCRIPT" && ok "remove-archived-skills.sh parses" || bad "remove-archived-skills.sh has a syntax error"

# mk_fixture <skills dir>: the box root is its parent, so retired copies land in <parent>/retired-skills
mk_fixture() {
  local s="$1"
  rm -rf "$(dirname "$s")"; mkdir -p "$s"
  # retired folders: one registered in the repo, one box-local that never came from the repo
  mkdir -p "$s/34-intelligent-staffing-ARCHIVED/specialist-templates" "$s/30-blackceo-voice-call-plugin-ARCHIVED"
  echo "gen1" > "$s/34-intelligent-staffing-ARCHIVED/SKILL.md"
  echo "nested" > "$s/34-intelligent-staffing-ARCHIVED/specialist-templates/a.md"
  echo "hand-made" > "$s/30-blackceo-voice-call-plugin-ARCHIVED/notes.md"
  # lookalikes that must survive
  mkdir -p "$s/45-archive-keeper" "$s/12-archived-notes" "$s/ARCHIVED-docs" "$s/99-x-ARCHIVED-copy" "$s/03-agent-browser"
  echo "live" > "$s/45-archive-keeper/SKILL.md"
  echo "live" > "$s/03-agent-browser/SKILL.md"
  echo "keep" > "$s/12-archived-notes/n.md"
  # a plain file that carries the suffix, a non-skill file, and a symlink with the suffix
  echo "file" > "$s/77-just-a-file-ARCHIVED"
  echo "marker" > "$s/.pending-setup.md"
  mkdir -p "$T/elsewhere"; echo "target" > "$T/elsewhere/t.md"
  ln -s "$T/elsewhere" "$s/55-linked-ARCHIVED"
}

S="$T/box/skills"; D="$T/box/retired-skills"
mk_fixture "$S"
out1="$(bash "$SCRIPT" "$S" 2>&1)"; rc1=$?
[ "$rc1" -eq 0 ] && ok "first run exits 0" || { bad "first run rc=$rc1"; echo "$out1"; }
[ ! -e "$S/34-intelligent-staffing-ARCHIVED" ] && [ ! -e "$S/30-blackceo-voice-call-plugin-ARCHIVED" ] \
  && ok "both retired folders are gone from the skills folder" || bad "a retired folder is still in the skills folder"
# moved, not deleted: content intact at the destination, which is OUTSIDE the skills folder
[ -f "$D/34-intelligent-staffing-ARCHIVED/SKILL.md" ] && [ "$(cat "$D/34-intelligent-staffing-ARCHIVED/SKILL.md" 2>/dev/null)" = "gen1" ] \
  && [ "$(cat "$D/34-intelligent-staffing-ARCHIVED/specialist-templates/a.md" 2>/dev/null)" = "nested" ] \
  && ok "registered retired folder MOVED to <parent>/retired-skills with its nested content intact" \
  || bad "registered retired folder was not moved intact to $D"
[ "$(cat "$D/30-blackceo-voice-call-plugin-ARCHIVED/notes.md" 2>/dev/null)" = "hand-made" ] \
  && ok "box-local retired folder (never in the repo) is kept in retired-skills, not destroyed" \
  || bad "box-local retired folder was deleted or lost its content"
case "$D" in "$S"|"$S"/*) bad "destination is inside the skills folder OpenClaw scans" ;; *) ok "destination is outside the skills folder" ;; esac
survivors_ok=1
for keep in 45-archive-keeper 12-archived-notes ARCHIVED-docs 99-x-ARCHIVED-copy 03-agent-browser; do
  [ -d "$S/$keep" ] || { survivors_ok=0; echo "  missing survivor: $keep"; }
done
[ -f "$S/45-archive-keeper/SKILL.md" ] && [ -f "$S/03-agent-browser/SKILL.md" ] && [ -f "$S/12-archived-notes/n.md" ] || survivors_ok=0
[ "$survivors_ok" -eq 1 ] && ok "lookalike and live skills untouched (name contains archive, no exact suffix)" || bad "a live or lookalike skill was moved or removed"
[ ! -e "$D/45-archive-keeper" ] && [ ! -e "$D/99-x-ARCHIVED-copy" ] && ok "nothing but the two retired folders reached retired-skills" || bad "a lookalike reached retired-skills"
[ -f "$S/77-just-a-file-ARCHIVED" ] && [ -f "$S/.pending-setup.md" ] && ok "plain files untouched" || bad "a plain file was moved or removed"
[ -L "$S/55-linked-ARCHIVED" ] && [ -f "$T/elsewhere/t.md" ] && ok "symlink named *-ARCHIVED and its target untouched" || bad "symlink or its target was touched"
echo "$out1" | grep -q "moved retired skill folder out of the skills folder: 34-intelligent-staffing-ARCHIVED -> $D/34-intelligent-staffing-ARCHIVED" \
  && echo "$out1" | grep -q "moved retired skill folder out of the skills folder: 30-blackceo-voice-call-plugin-ARCHIVED -> " \
  && ok "each move is logged by name with its destination" || { bad "move log lines missing"; echo "$out1"; }

before="$(cd "$T/box" && find . | LC_ALL=C sort)"
out2="$(bash "$SCRIPT" "$S" 2>&1)"; rc2=$?
after="$(cd "$T/box" && find . | LC_ALL=C sort)"
if [ "$rc2" -eq 0 ] && [ "$before" = "$after" ] && [ -z "$out2" ]; then
  ok "second run is a silent no-op (nothing moved, no output, rc 0, symlink skipped quietly)"
else
  bad "second run was not a silent no-op: rc=$rc2 out=[$out2]"
fi

# a second dir of the same name later never overwrites the first retired copy (suffix, then counter)
mkdir -p "$S/34-intelligent-staffing-ARCHIVED"; echo "gen2" > "$S/34-intelligent-staffing-ARCHIVED/SKILL.md"
bash "$SCRIPT" "$S" >/dev/null 2>&1; rcg2=$?
mkdir -p "$S/34-intelligent-staffing-ARCHIVED"; echo "gen3" > "$S/34-intelligent-staffing-ARCHIVED/SKILL.md"
bash "$SCRIPT" "$S" >/dev/null 2>&1; rcg3=$?
copies=0; seen=""
for c in "$D"/34-intelligent-staffing-ARCHIVED*; do
  [ -d "$c" ] || continue
  copies=$((copies + 1)); seen="$seen $(cat "$c/SKILL.md" 2>/dev/null)"
done
if [ "$rcg2" -eq 0 ] && [ "$rcg3" -eq 0 ] && [ "$copies" -eq 3 ] && [ "$(cat "$D/34-intelligent-staffing-ARCHIVED/SKILL.md")" = "gen1" ] \
   && echo "$seen" | grep -q gen2 && echo "$seen" | grep -q gen3 && [ ! -e "$S/34-intelligent-staffing-ARCHIVED" ]; then
  ok "same-name retired dirs get unique destinations (3 copies kept, the first never overwritten)"
else
  bad "same-name handling wrong: copies=$copies seen=[$seen] rc=$rcg2/$rcg3"
fi

# default skills folder resolution: OPENCLAW_ROOT/skills (the same variable update-skills.sh honors)
mk_fixture "$T/oc/skills"
env -u OC_SKILLS_DIR -u OC_CONFIG OPENCLAW_ROOT="$T/oc" HOME="$T/nohome" bash "$SCRIPT" >/dev/null 2>&1
[ ! -e "$T/oc/skills/34-intelligent-staffing-ARCHIVED" ] && [ -d "$T/oc/retired-skills/34-intelligent-staffing-ARCHIVED" ] && [ -d "$T/oc/skills/45-archive-keeper" ] \
  && ok "no-argument call resolves \$OPENCLAW_ROOT/skills and retires into \$OPENCLAW_ROOT/retired-skills" || bad "default resolution missed the skills folder"

# missing folder is not an error
bash "$SCRIPT" "$T/does-not-exist" >/dev/null 2>&1 && ok "missing skills folder exits 0" || bad "missing skills folder was an error"

# an unmovable retired folder is reported, exits 1, stays in place, and never touches the rest (skipped as root)
if [ "$(id -u)" != "0" ]; then
  mk_fixture "$T/lk/skills"
  chmod a-w "$T/lk/skills"
  errout="$(bash "$SCRIPT" "$T/lk/skills" 2>&1)"; rcl=$?
  chmod u+w "$T/lk/skills"
  [ "$rcl" -eq 1 ] && echo "$errout" | grep -q "could not move retired skill folder" && [ -d "$T/lk/skills/45-archive-keeper" ] \
    && [ "$(cat "$T/lk/skills/34-intelligent-staffing-ARCHIVED/SKILL.md" 2>/dev/null)" = "gen1" ] \
    && ok "unmovable folder is reported (rc 1) and left intact, live skills untouched" || { bad "unmovable-folder handling wrong: rc=$rcl"; echo "$errout"; }
fi

# ---- (3) wiring: the roll actually calls it --------------------------------------------------
U="$TREE/update-skills.sh"; I="$TREE/install.sh"
call_line="$(grep -n 'remove-archived-skills.sh" "\$SKILLS_DIR"' "$U" | head -1 | cut -d: -f1)"
recheck_line="$(grep -n 'CONTENT RECHECK (stamp already current' "$U" | head -1 | cut -d: -f1)"
wired_line="$(grep -n 'WIRED_SENTINEL="\$SKILL_DIR/.wired-' "$U" | head -1 | cut -d: -f1)"
if [ -n "$call_line" ] && [ -n "$recheck_line" ] && [ -n "$wired_line" ]; then
  [ "$call_line" -lt "$recheck_line" ] && ok "update-skills.sh clears retired folders before the content-recheck early exit (line $call_line < $recheck_line)" \
    || bad "update-skills.sh cleanup is after the content-recheck early exit"
  [ "$call_line" -lt "$wired_line" ] && ok "cleanup sits outside the per-version .wired sentinel (line $call_line < $wired_line)" \
    || bad "cleanup is not ahead of the .wired sentinel loop"
else
  bad "update-skills.sh wiring not found (call=$call_line recheck=$recheck_line wired=$wired_line)"
fi
grep -q 'remove-archived-skills.sh' "$I" && ok "install.sh calls the cleanup before installing" || bad "install.sh does not call the cleanup"

# run the REAL call block lifted out of update-skills.sh against a fixture, so a typo in the wiring fails here
blk="$T/call-block.sh"
awk '/^  if \[ -f "\$EXTRACTED_DIR\/scripts\/remove-archived-skills.sh" \]; then$/{f=1} f{print} f&&/^  fi$/{exit}' "$U" > "$blk"
if [ -s "$blk" ] && bash -n "$blk"; then
  mk_fixture "$T/w/skills"
  EXTRACTED_DIR="$TREE" SKILLS_DIR="$T/w/skills" bash "$blk" >/dev/null 2>&1
  [ ! -e "$T/w/skills/34-intelligent-staffing-ARCHIVED" ] && [ -d "$T/w/retired-skills/34-intelligent-staffing-ARCHIVED" ] && [ -d "$T/w/skills/45-archive-keeper" ] \
    && ok "the call block as written in update-skills.sh clears a fixture box" || bad "the lifted call block did not clear the fixture"
else
  bad "could not lift the call block out of update-skills.sh"
fi

exit $fail

#!/usr/bin/env bash
# skills-rollback-no-copy.test.sh — update-skills.sh no longer copies the skills folder
# before an update, and the no-copy rollback still gets a box back.
#
# Before: every update wrote a full skills-backup-<ts> copy of ~/.openclaw/skills (hundreds
# of MB each) into ~/Downloads/openclaw-backups. Now scripts/skills-rollback.sh records the
# previous commit plus a patch of this box's local changes, and restores from git.
#
#   T1  snapshot of a box with a recorded commit -> exit 0
#   T2  the snapshot holds NO copy of the skills folder: no directories, a few KB
#   T3  the local-changes patch carries the edit, the deletion and the extra file,
#       and leaves caches (node_modules, __pycache__) out
#   T4  after an update to a newer commit, restore puts back the previous commit's files,
#       re-applies the local changes, removes the folder the update added, keeps the box's
#       custom skill, and restores the version stamp + manifest
#   T5  a box with no recorded commit -> exit 3 (caller must use its fallback), nothing written
#   T6  a version-tag-only box (no manifest sha) still resolves through refs/tags/<version>
#   T7  update-skills.sh calls the snapshot and no longer copies the folder on the normal path
#   C1  ANTI-FALSE-PASS: a real full copy of the skills folder FAILS the T2 predicate
#
# Hermetic: a local file:// origin in a tempdir. No network, no real box.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO_ROOT/scripts/skills-rollback.sh"
UPDATER="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
pass() { echo "PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "FAIL  $1"; FAIL=$((FAIL+1)); }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
q() { git -c init.defaultBranch=main "$@" >/dev/null 2>&1; }

# ── origin with two commits ──────────────────────────────────────────────────
ORIGIN="$TMP/origin"; mkdir -p "$ORIGIN"; q -C "$ORIGIN" init
q -C "$ORIGIN" config uploadpack.allowAnySHA1InWant true
mkdir -p "$ORIGIN/01-alpha" "$ORIGIN/shared-utils" "$ORIGIN/universal-sops" "$ORIGIN/docs"
printf 'alpha skill v1\n' > "$ORIGIN/01-alpha/SKILL.md"
printf 'a v1\n'          > "$ORIGIN/01-alpha/a.txt"
printf 'gone locally\n'  > "$ORIGIN/01-alpha/removed-by-box.txt"
printf 'util v1\n'       > "$ORIGIN/shared-utils/u.sh"
printf 'sop v1\n'        > "$ORIGIN/universal-sops/s.md"
printf 'not installed\n' > "$ORIGIN/docs/readme.md"
q -C "$ORIGIN" add -A; q -C "$ORIGIN" commit -m A; q -C "$ORIGIN" tag v1.0.0
A=$(git -C "$ORIGIN" rev-parse HEAD)
printf 'a v2\n'          > "$ORIGIN/01-alpha/a.txt"
printf 'util v2\n'       > "$ORIGIN/shared-utils/u.sh"
mkdir -p "$ORIGIN/02-beta"; printf 'beta\n' > "$ORIGIN/02-beta/SKILL.md"
q -C "$ORIGIN" add -A; q -C "$ORIGIN" commit -m B
B=$(git -C "$ORIGIN" rev-parse HEAD)
export ONBOARDING_REPO_URL="file://$ORIGIN"

install_commit() {  # <commit> <skills-dir> : what update-skills.sh does for the repo-owned folders
  local c=$1 s=$2 n
  for n in 01-alpha 02-beta shared-utils universal-sops; do rm -rf "${s:?}/$n"; done
  git -C "$ORIGIN" archive "$c" 01-alpha shared-utils universal-sops $(git -C "$ORIGIN" ls-tree --name-only "$c" | grep '^02-beta$') \
    | tar -x -C "$s"
  printf '{"version": "%s", "src_git_sha": "%s"}\n' "$3" "$c" > "$s/.onboarding-content-manifest.json"
  printf '%s\n' "$3" > "$s/.onboarding-version"
}

# ── a box on commit A with local changes ────────────────────────────────────
SK="$TMP/box/skills"; mkdir -p "$SK"
install_commit "$A" "$SK" v1.0.0
printf 'alpha skill v1\nLOCAL EDIT\n' > "$SK/01-alpha/SKILL.md"
rm "$SK/01-alpha/removed-by-box.txt"
printf 'box-made notes\n' > "$SK/01-alpha/notes.md"
mkdir -p "$SK/01-alpha/node_modules/pkg" "$SK/shared-utils/__pycache__"
head -c 2000000 /dev/zero > "$SK/01-alpha/node_modules/pkg/big.bin"
printf 'x' > "$SK/shared-utils/__pycache__/u.cpython-312.pyc"
mkdir -p "$SK/my-custom-skill"; printf 'mine\n' > "$SK/my-custom-skill/SKILL.md"

no_full_copy() {  # <dir> : true when <dir> holds no directory and is under 64 KB
  [ -z "$(find "$1" -mindepth 1 -type d)" ] && [ "$(du -sk "$1" | cut -f1)" -lt 64 ]
}

# ── T1-T3 snapshot ──────────────────────────────────────────────────────────
OUT="$TMP/backups/skills-rollback-1"
if bash "$SCRIPT" snapshot "$SK" "$OUT" > "$TMP/snap.log" 2>&1; then pass "T1 snapshot exit 0"; else fail "T1 snapshot failed: $(cat "$TMP/snap.log")"; fi
if no_full_copy "$OUT"; then pass "T2 snapshot holds no copy of the skills folder ($(du -sk "$OUT" | cut -f1) KB, no directories)"
else fail "T2 snapshot is a copy: $(find "$OUT" | head -5)"; fi
P="$OUT/local-changes.patch"
if grep -q 'LOCAL EDIT' "$P" && grep -q 'removed-by-box.txt' "$P" && grep -q 'notes.md' "$P"; then pass "T3a patch carries the edit, the deletion and the extra file"
else fail "T3a patch incomplete: $(cat "$P")"; fi
if ! grep -qE 'node_modules|__pycache__' "$P"; then pass "T3b caches are left out of the patch"; else fail "T3b caches leaked into the patch"; fi
if grep -q "\"commit\": \"$A\"" "$OUT/rollback.json"; then pass "T3c rollback.json records the previous commit"; else fail "T3c wrong commit: $(cat "$OUT/rollback.json")"; fi

# ── T4 update to B, then restore ─────────────────────────────────────────────
install_commit "$B" "$SK" v2.0.0
if bash "$SCRIPT" restore "$OUT" > "$TMP/restore.log" 2>&1; then pass "T4a restore exit 0"; else fail "T4a restore failed: $(cat "$TMP/restore.log")"; fi
T4=1
[ "$(cat "$SK/01-alpha/a.txt")" = "a v1" ]                || { T4=0; echo "  a.txt not back to v1"; }
[ "$(cat "$SK/shared-utils/u.sh")" = "util v1" ]          || { T4=0; echo "  u.sh not back to v1"; }
grep -q 'LOCAL EDIT' "$SK/01-alpha/SKILL.md"              || { T4=0; echo "  local edit lost"; }
[ -f "$SK/01-alpha/notes.md" ]                            || { T4=0; echo "  extra file lost"; }
[ ! -e "$SK/01-alpha/removed-by-box.txt" ]                || { T4=0; echo "  local deletion not re-applied"; }
[ ! -e "$SK/02-beta" ]                                    || { T4=0; echo "  folder added by the update not removed"; }
[ "$(cat "$SK/my-custom-skill/SKILL.md")" = "mine" ]      || { T4=0; echo "  custom skill touched"; }
[ "$(cat "$SK/.onboarding-version")" = "v1.0.0" ]         || { T4=0; echo "  version stamp not restored"; }
grep -q "$A" "$SK/.onboarding-content-manifest.json"      || { T4=0; echo "  manifest not restored"; }
[ ! -e "$SK/docs" ]                                       || { T4=0; echo "  non-installed repo folder leaked in"; }
if [ "$T4" = 1 ]; then pass "T4b box is back on commit A with its local changes, custom skill intact"; else fail "T4b restore incomplete"; fi

# ── T5 no recorded commit ────────────────────────────────────────────────────
BARE="$TMP/bare/skills"; mkdir -p "$BARE/01-alpha"; printf 'x\n' > "$BARE/01-alpha/SKILL.md"
bash "$SCRIPT" snapshot "$BARE" "$TMP/backups/none" > "$TMP/none.log" 2>&1; RC=$?
if [ "$RC" = 3 ] && [ ! -e "$TMP/backups/none" ]; then pass "T5 no recorded commit -> exit 3, nothing written"
else fail "T5 expected exit 3 and no output, got rc=$RC"; fi

# ── T6 version tag only ──────────────────────────────────────────────────────
TAGBOX="$TMP/tagbox/skills"; mkdir -p "$TAGBOX"; install_commit "$A" "$TAGBOX" v1.0.0
rm "$TAGBOX/.onboarding-content-manifest.json"
if bash "$SCRIPT" snapshot "$TAGBOX" "$TMP/backups/tag" > "$TMP/tag.log" 2>&1 && grep -q "\"commit\": \"$A\"" "$TMP/backups/tag/rollback.json"; then
  pass "T6 version-tag-only box resolves refs/tags/v1.0.0 to commit A"
else fail "T6 tag resolution failed: $(cat "$TMP/tag.log")"; fi

# ── T7 wiring in update-skills.sh ────────────────────────────────────────────
BLOCK=$(awk '/NO-SKILLS-BACKUP-COPY-V1/{f=1} f{print} /END NO-SKILLS-BACKUP-COPY-V1/{exit}' "$UPDATER")
if printf '%s' "$BLOCK" | grep -q 'skills-rollback.sh" snapshot'; then pass "T7a update-skills.sh records the no-copy rollback"; else fail "T7a snapshot call missing"; fi
NORMAL=$(printf '%s\n' "$BLOCK" | awk '/_rb_rc" -eq 3/{exit} {print}')
if ! printf '%s' "$NORMAL" | grep -qE 'cp -r "\$SKILLS_DIR"'; then pass "T7b the normal path copies nothing"; else fail "T7b a full copy is still on the normal path"; fi
if [ "$(grep -cE 'cp -r "\$SKILLS_DIR"/\* ' "$UPDATER")" -le 1 ]; then pass "T7c at most one full-copy line remains (the no-commit fallback)"; else fail "T7c extra full-copy lines"; fi

# ── C1 anti-false-pass ───────────────────────────────────────────────────────
mkdir -p "$TMP/fullcopy"; cp -r "$SK"/. "$TMP/fullcopy/"
if no_full_copy "$TMP/fullcopy"; then fail "C1 CONTROL BLIND: a full copy passed the no-copy predicate"
else pass "C1 control: a real full copy fails the no-copy predicate"; fi

echo "----"; echo "PASS=$PASS FAIL=$FAIL"
[ "$FAIL" = 0 ]

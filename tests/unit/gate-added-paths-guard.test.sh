#!/usr/bin/env bash
# gate-added-paths-guard.test.sh — runnable controls for tools/gate-added-paths.sh
#
# Four controls, each asserting an EXACT exit code:
#   a) a change that adds exactly one volume-root line     -> exit 1
#   b) a clean add on a history that already carries the volume root -> exit 0
#      (added-lines-only must not fail on pre-existing text). This runs on the
#      fixture, never on live main: main gains banned-path lines through
#      unrelated merges, which made the control fail for every PR.
#   c) missing repo / unreadable ref                     -> exit 2
#   d) a change that adds only /home/ and /private/      -> exit 0
#      (D-27: /home/ and /private/ are NOT banned)
#
# Usage: bash tests/unit/gate-added-paths-guard.test.sh
# Exit: 0 all controls behaved, 1 any control misbehaved, 2 instrument error.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
GUARD="$REPO_ROOT/tools/gate-added-paths.sh"

[ -f "$GUARD" ] || { echo "INSTRUMENT_ERROR: guard not found: $GUARD" >&2; exit 2; }

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

FAILS=0
check() { # <name> <expected> <actual>
  if [ "$2" = "$3" ]; then
    echo "PASS  $1 (exit $3)"
  else
    echo "FAIL  $1 (expected $2, got $3)"
    FAILS=$((FAILS + 1))
  fi
}

# ── fixture repo: baseline already carries a volume path and the unbanned roots ──
# Host roots are assembled at runtime from parts: the committed source must not
# carry either literal, or this fixture trips the very gate it exercises.
VOL="/Vol"; VOL+="umes"
USR="/Us"; USR+="ers"
MOUNT="$VOL/fixture-mount"
LEAK="$MOUNT/Downloads/out.txt"
USER_LEAK="$USR/tester/notes.txt"

FX="$TMP/fixture"
mkdir -p "$FX"
git -C "$FX" init -q
git -C "$FX" config user.email guard@example.invalid
git -C "$FX" config user.name guard
printf '%s\n' \
  "mount=$MOUNT/old-copy" \
  'docker=/home/hatch/app' \
  'private=/private/tmp/work' > "$FX/baseline.txt"
git -C "$FX" add -A
git -C "$FX" commit -qm baseline
BASE="$(git -C "$FX" rev-parse HEAD)"

# a) exactly one added volume line -> 1
printf '%s\n' "leak=$LEAK" > "$FX/leak.txt"
git -C "$FX" add -A
git -C "$FX" commit -qm add-volumes-leak
bash "$GUARD" "$FX" "$BASE" HEAD > "$TMP/a.out" 2>&1; rc_a=$?
sed 's/^/    /' "$TMP/a.out"
check "a) one added volume-root line" 1 "$rc_a"

# u) exactly one added user-home line -> 1
USR_BASE="$(git -C "$FX" rev-parse HEAD)"
printf '%s\n' "notes=$USER_LEAK" > "$FX/userleak.txt"
git -C "$FX" add -A
git -C "$FX" commit -qm add-user-home-leak
bash "$GUARD" "$FX" "$USR_BASE" HEAD > "$TMP/u.out" 2>&1; rc_u=$?
sed 's/^/    /' "$TMP/u.out"
check "u) one added user-home line" 1 "$rc_u"

# d) only /home/ and /private/ added -> 0 (must NOT be banned)
HOME_ONLY_BASE="$(git -C "$FX" rev-parse HEAD)"
printf '%s\n' \
  'docker=/home/node/workspace' \
  'private=/private/tmp/scratch' > "$FX/dockerpaths.txt"
git -C "$FX" add -A
git -C "$FX" commit -qm add-home-and-private
bash "$GUARD" "$FX" "$HOME_ONLY_BASE" HEAD > "$TMP/d.out" 2>&1; rc_d=$?
sed 's/^/    /' "$TMP/d.out"
check "d) /home/ and /private/ not banned" 0 "$rc_d"

# b) pre-existing banned text in history must not fail an added-lines scan.
#    Run against the fixture, not this repo's live main: main gains banned-path
#    lines over time through unrelated merges, which made this control fail for
#    every PR regardless of what the PR contained.
CLEAN_BASE="$(git -C "$FX" rev-parse HEAD)"
printf '%s\n' 'note=no host paths here' > "$FX/clean.txt"
git -C "$FX" add -A
git -C "$FX" commit -qm add-clean-line
bash "$GUARD" "$FX" "$CLEAN_BASE" HEAD > "$TMP/b.out" 2>&1; rc_b=$?
sed 's/^/    /' "$TMP/b.out"
check "b) clean add over a history that already carries host roots" 0 "$rc_b"

# c) instrument errors -> 2
bash "$GUARD" "$TMP/does-not-exist" "$BASE" HEAD > "$TMP/c1.out" 2>&1; rc_c1=$?
sed 's/^/    /' "$TMP/c1.out"
check "c1) missing repo" 2 "$rc_c1"

bash "$GUARD" "$FX" "$BASE" deadbeefdeadbeefdeadbeefdeadbeefdeadbeef > "$TMP/c2.out" 2>&1; rc_c2=$?
sed 's/^/    /' "$TMP/c2.out"
check "c2) unresolvable head ref" 2 "$rc_c2"

bash "$GUARD" > "$TMP/c3.out" 2>&1; rc_c3=$?
sed 's/^/    /' "$TMP/c3.out"
check "c3) missing arguments" 2 "$rc_c3"

# positive control: the instrument itself must be able to see added lines
bash "$GUARD" "$FX" "$HOME_ONLY_BASE" HEAD --positive-control > "$TMP/pc.out" 2>&1; rc_pc=$?
sed 's/^/    /' "$TMP/pc.out"
check "positive control) instrument parses added lines" 0 "$rc_pc"

echo
if [ "$FAILS" -gt 0 ]; then
  echo "RESULT: FAIL — $FAILS control(s) misbehaved"
  exit 1
fi
echo "RESULT: PASS — all controls behaved"
exit 0

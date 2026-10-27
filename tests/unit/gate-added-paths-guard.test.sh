#!/usr/bin/env bash
# gate-added-paths-guard.test.sh — runnable controls for tools/gate-added-paths.sh
#
# Four controls, each asserting an EXACT exit code:
#   a) a change that adds exactly one /Volumes/ line      -> exit 1
#   b) origin/main~1...origin/main on this repo          -> exit 0
#      (main already carries /Volumes/ in 42 files; added-lines-only must not
#       fail on pre-existing text)
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
# Host paths are assembled at runtime: the committed source must not carry one,
# or this fixture trips the very gate it exercises.
VOL=/Volumes
MOUNT="$VOL/fixture-mount"
LEAK="$MOUNT/Downloads/out.txt"

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
check "a) one added /Volumes/ line" 1 "$rc_a"

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

# b) this repo's own merged main must be clean: pre-existing /Volumes/ text is
#    not in the added set for the tip commit.
if git -C "$REPO_ROOT" rev-parse --verify --quiet origin/main~1 >/dev/null 2>&1; then
  bash "$GUARD" "$REPO_ROOT" origin/main~1 origin/main > "$TMP/b.out" 2>&1; rc_b=$?
  sed 's/^/    /' "$TMP/b.out"
  check "b) origin/main~1...origin/main" 0 "$rc_b"
else
  echo "FAIL  b) origin/main~1 unresolvable — control cannot run"
  FAILS=$((FAILS + 1))
fi

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

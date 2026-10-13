#!/usr/bin/env bash
# tests/unit/cc-fast-path-never-discards-local-commits.test.sh
# D01: the CONVERGENCE-FAST-PATH ran `git reset --hard origin/main` on any CLEAN
# Command Center checkout, so a diverged checkout (local commits not on origin)
# lost them. The extracted block must now fast-forward only: a behind checkout
# still catches up, a diverged one keeps its local commits. Offline, real git.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $*"; }
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
G() { git -c user.email=t@e.com -c user.name=T -c commit.gpgsign=false "$@"; }

# Only the CC-currency repair loop (up to the DB resolver), verbatim from the marker block.
awk '/>>> CONVERGENCE-FAST-PATH-BEGIN/{p=1;next} /<<< CONVERGENCE-FAST-PATH-END/{p=0} p{print}' "$UPDATER" \
  | awk '/the Command Center DB both SOP repairs below read/{exit} {print}' > "$WORK/fast.inc"
echo fi >> "$WORK/fast.inc"   # closes the block's outer `if drift ... else` cut off above
[ -s "$WORK/fast.inc" ] && grep -q '_fast_sync' "$WORK/fast.inc" || { echo "FATAL: fast-path block not extracted (marker drift?)"; exit 2; }

run_fast() { # <box dir>; the block is a loop over candidate dirs, CC_APP_DIR picks ours
  ( HOME="$WORK/home"; CC_APP_DIR="$1"; _RECHECK_DRIFT=""; export HOME CC_APP_DIR
    # shellcheck source=/dev/null
    source "$WORK/fast.inc" ) 2>&1
}

mk() { # <name>: bare origin (remote url contains "command-center") + pusher + box clone
  local n="$1"
  git init -q --bare -b main "$WORK/$n-command-center.git"
  git clone -q "$WORK/$n-command-center.git" "$WORK/$n-push" 2>/dev/null
  printf 'a1\n' > "$WORK/$n-push/A.txt"; G -C "$WORK/$n-push" add -A
  G -C "$WORK/$n-push" commit -q -m init; G -C "$WORK/$n-push" push -q origin HEAD:main
  git clone -q "$WORK/$n-command-center.git" "$WORK/$n-box" 2>/dev/null
}
upstream() { printf 'up\n' > "$WORK/$1-push/U.txt"; G -C "$WORK/$1-push" add -A; G -C "$WORK/$1-push" commit -q -m up; G -C "$WORK/$1-push" push -q origin HEAD:main; }

echo "== (a) clean tree, behind origin: fast-forwards =="
mk a; upstream a; BOX="$WORK/a-box"
run_fast "$BOX" >/dev/null
[ -f "$BOX/U.txt" ] && ok "(a) box caught up to origin/main" || bad "(a) box did not fast-forward"

echo "== (b) clean tree, DIVERGED (local commit + upstream moved): local commit survives =="
mk b; BOX="$WORK/b-box"
printf 'local\n' > "$BOX/L.txt"; G -C "$BOX" add -A; G -C "$BOX" commit -q -m local-only
LOCAL="$(git -C "$BOX" rev-parse HEAD)"
upstream b
out="$(run_fast "$BOX")"
git -C "$BOX" merge-base --is-ancestor "$LOCAL" HEAD && [ -f "$BOX/L.txt" ] \
  && ok "(b) local commit still in HEAD, file intact" || bad "(b) local commit was discarded (reset --hard?)"
[ "$(git -C "$BOX" rev-parse HEAD)" = "$LOCAL" ] && ok "(b) HEAD untouched" || bad "(b) HEAD moved"
printf '%s' "$out" | grep -q 'could not be refreshed' && ok "(b) refused, leaves it to the full pass" || bad "(b) no refusal message: $out"

echo "== (c) no reset --hard left in the block =="
grep -q 'reset --hard"' "$WORK/fast.inc" && bad "(c) block still sets reset --hard" || ok "(c) no reset --hard"

echo "passed=$PASS failed=$FAIL"; [ "$FAIL" = 0 ]

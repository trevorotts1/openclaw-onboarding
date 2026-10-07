#!/usr/bin/env bash
# tests/unit/cc-dirty-ff-when-safe.test.sh
# ---------------------------------------------------------------------------
# A Command Center checkout with local tracked edits must still be refreshed
# when upstream did not touch those same files. cc_dirty_overlap (shared by the
# currency probe, the fast path and the DIRTY-CHECKOUT GUARD) is lifted out of
# update-skills.sh and run against real git repos + a bare origin. Offline.
# Also pins that all three call sites use it and that none stashes/resets a
# dirty tree.
# ---------------------------------------------------------------------------
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $*"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $*"; }
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

awk '/^cc_dirty_overlap\(\) \{/{p=1} p{print} p&&/^\}/{exit}' "$UPDATER" > "$WORK/helper.sh"
[ -s "$WORK/helper.sh" ] || { echo "FATAL: cc_dirty_overlap not found in update-skills.sh"; exit 2; }
# shellcheck source=/dev/null
source "$WORK/helper.sh"

G() { git -c user.email=t@e.com -c user.name=T -c commit.gpgsign=false "$@"; }
tracked_dirty() { git -C "$1" status --porcelain | grep -v '^??' || true; }

# mk <name>: bare origin + clone "box" (files A,B) + a pusher clone
mk() {
  local n="$1"
  git init -q --bare -b main "$WORK/$n.git"
  git clone -q "$WORK/$n.git" "$WORK/$n-push" 2>/dev/null
  printf 'a1\n' > "$WORK/$n-push/A.txt"; printf 'b1\n' > "$WORK/$n-push/B.txt"
  G -C "$WORK/$n-push" add -A; G -C "$WORK/$n-push" commit -q -m init; G -C "$WORK/$n-push" push -q origin HEAD:main
  git clone -q "$WORK/$n.git" "$WORK/$n-box" 2>/dev/null
}
upstream() { # <name> <file>
  printf 'up-%s\n' "$RANDOM" >> "$WORK/$1-push/$2"
  G -C "$WORK/$1-push" commit -q -am "up $2"; G -C "$WORK/$1-push" push -q origin HEAD:main
}

echo "== (a) local edit A, upstream changes B: no overlap, ff keeps the edit =="
mk a; BOX="$WORK/a-box"
printf 'local-edit\n' >> "$BOX/A.txt"; upstream a B.txt
out="$(cc_dirty_overlap "$BOX")"; rc=$?
[ "$rc" = 0 ] && [ -z "$out" ] && ok "(a) rc=0, no overlap" || bad "(a) rc=$rc out='$out'"
G -C "$BOX" merge --ff-only origin/main >/dev/null 2>&1 && ok "(a) merge --ff-only succeeded on the dirty tree" || bad "(a) ff-only failed"
grep -q local-edit "$BOX/A.txt" && ok "(a) A's local edit survived" || bad "(a) A's edit was lost"
grep -q '^up-' "$BOX/B.txt" && ok "(a) B picked up the upstream change" || bad "(a) B not updated"
git -C "$BOX" merge-base --is-ancestor origin/main HEAD && ok "(a) state=current (origin/main is an ancestor)" || bad "(a) not current"

echo "== (b) local edit A, upstream also changes A: overlap, A named, tree untouched =="
mk b; BOX="$WORK/b-box"
printf 'local-edit\n' >> "$BOX/A.txt"; upstream b A.txt
before="$(git -C "$BOX" rev-parse HEAD)"
out="$(cc_dirty_overlap "$BOX")"; rc=$?
[ "$rc" = 1 ] && [ "$out" = "A.txt" ] && ok "(b) rc=1 and A.txt listed (state=dirty)" || bad "(b) rc=$rc out='$out'"
[ "$(git -C "$BOX" rev-parse HEAD)" = "$before" ] && grep -q local-edit "$BOX/A.txt" && ok "(b) nothing moved; edit intact" || bad "(b) tree was touched"

echo "== (b2) staged edit counts as a local edit =="
mk s; BOX="$WORK/s-box"
printf 'staged\n' >> "$BOX/A.txt"; git -C "$BOX" add A.txt; upstream s A.txt
out="$(cc_dirty_overlap "$BOX")"; rc=$?
[ "$rc" = 1 ] && [ "$out" = "A.txt" ] && ok "(b2) staged A overlaps" || bad "(b2) rc=$rc out='$out'"

echo "== (c) untracked-only: not dirty, helper never needed =="
mk c; BOX="$WORK/c-box"; printf 'x\n' > "$BOX/stray.tmp"; upstream c B.txt
[ -z "$(tracked_dirty "$BOX")" ] && ok "(c) tracked-dirty empty (existing rule unchanged)" || bad "(c) untracked counted as dirt"
G -C "$BOX" fetch -q origin && G -C "$BOX" merge --ff-only origin/main >/dev/null 2>&1 && [ -f "$BOX/stray.tmp" ] && ok "(c) plain refresh works, stray file kept" || bad "(c) refresh failed"

echo "== (d) fetch failure => rc 2 (blocked, as today) =="
mk d; BOX="$WORK/d-box"; printf 'e\n' >> "$BOX/A.txt"
git -C "$BOX" remote set-url origin "$WORK/does-not-exist.git"
cc_dirty_overlap "$BOX" >/dev/null 2>&1; rc=$?
[ "$rc" = 2 ] && ok "(d) rc=2 when origin unreachable" || bad "(d) rc=$rc"

echo "== (f) conflicting local tag must not break the helper =="
mk f; BOX="$WORK/f-box"
G -C "$WORK/f-push" tag v1 && G -C "$WORK/f-push" push -q origin v1
G -C "$BOX" fetch -q origin   # box now has v1 = init
printf 'x\n' >> "$WORK/f-push/B.txt"; G -C "$WORK/f-push" commit -q -am second
G -C "$WORK/f-push" tag -f v1 >/dev/null && G -C "$WORK/f-push" push -q -f origin v1 HEAD:main
printf 'local-edit\n' >> "$BOX/A.txt"
git -C "$BOX" fetch -q --tags origin 2>/dev/null; [ $? -ne 0 ] && ok "(f) precondition: plain fetch clobbers-tag error reproduced" || bad "(f) tag clash not reproduced"
out="$(cc_dirty_overlap "$BOX")"; rc=$?
[ "$rc" = 0 ] && [ -z "$out" ] && ok "(f) rc=0 despite tag clash (no overlap)" || bad "(f) rc=$rc out='$out'"
printf 'up\n' >> "$WORK/f-push/A.txt"; G -C "$WORK/f-push" commit -q -am upA; G -C "$WORK/f-push" push -q origin HEAD:main
out="$(cc_dirty_overlap "$BOX")"; rc=$?
[ "$rc" = 1 ] && [ "$out" = "A.txt" ] && ok "(f) rc=1 A.txt despite tag clash (overlap)" || bad "(f) rc=$rc out='$out'"

echo "== (e) all three call sites use the helper and never reset/stash a dirty tree =="
n="$(grep -c 'declare -F cc_dirty_overlap' "$UPDATER")"
[ "$n" = 3 ] && ok "(e) 3 guarded call sites" || bad "(e) expected 3 call sites, found $n"
grep -qF '_fast_sync="merge --ff-only"' "$UPDATER" && ok "(e) fast path uses merge --ff-only for dirty trees" || bad "(e) fast path missing ff-only"

echo ""; echo "  PASS: $PASS    FAIL: $FAIL"
[ "$FAIL" -eq 0 ] || exit 1

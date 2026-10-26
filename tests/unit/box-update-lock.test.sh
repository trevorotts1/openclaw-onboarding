#!/usr/bin/env bash
# Contract test: one box, one update owner — scripts/box-update-lock.sh.
# No framework: assert-based, exits non-zero on any failure.
set -u
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LOCK_SH="$HERE/../../scripts/box-update-lock.sh"
pass=0; fail=0
ok(){ pass=$((pass+1)); echo "  PASS: $1"; }
bad(){ fail=$((fail+1)); echo "  FAIL: $1"; }
[ -f "$LOCK_SH" ] || { echo "FATAL: missing $LOCK_SH"; exit 1; }

T="$(mktemp -d)" || exit 1
SLEEPER=""
cleanup(){ [ -n "$SLEEPER" ] && kill "$SLEEPER" 2>/dev/null; rm -rf "$T"; }
trap cleanup EXIT
start_of(){ ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//'; }

sleep 300 & SLEEPER=$!
S="$(start_of "$SLEEPER")"
[ -n "$S" ] || { echo "FATAL: cannot read process start identity"; exit 1; }

# 1. A live recorded owner is never displaced: a second writer REFUSES.
L="$T/live.lock"
printf 'pid=%s\nstart=%s\nrun_id=holder\nrole=test\n' "$SLEEPER" "$S" > "$L"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run test >/dev/null 2>&1; exit $? ); rc=$?
[ "$rc" = 3 ] && ok "a LIVE recorded owner means REFUSE (rc=3)" || bad "live owner not refused (rc=$rc)"

# 2. A dead owner is reclaimed, not waited on forever.
L="$T/stale.lock"
printf 'pid=999999\nstart=gone\nrun_id=dead\nrole=test\n' > "$L"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run test >/dev/null 2>&1; exit $? ); rc=$?
[ "$rc" = 0 ] && ok "a DEAD recorded owner is reclaimed (rc=0)" || bad "stale lease not reclaimed (rc=$rc)"

# 3. pid reuse: the same pid with a different start identity is not the owner.
L="$T/reuse.lock"
printf 'pid=%s\nstart=not-this-process\nrun_id=x\nrole=test\n' "$SLEEPER" > "$L"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run test >/dev/null 2>&1; exit $? ); rc=$?
[ "$rc" = 0 ] && ok "a reused pid with a different start identity is not a live owner" || bad "pid-reuse guard failed (rc=$rc)"

# 4. A non-owner release never deletes someone else's lease.
L="$T/notmine.lock"
printf 'pid=%s\nstart=%s\nrun_id=other\nrole=test\n' "$SLEEPER" "$S" > "$L"
( . "$LOCK_SH"; BUL_LOCK_PATH="$L"; box_update_lock_release )
[ -f "$L" ] && ok "a non-owner release leaves the lease in place" || bad "non-owner release deleted the lease"

# 5. The owner's release removes it.
L="$T/mine.lock"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run test >/dev/null 2>&1; box_update_lock_release; [ -f "$L" ] && exit 1 || exit 0 ); rc=$?
[ "$rc" = 0 ] && ok "the owner's release removes the lease" || bad "owner release left the lease"

# 6. The record carries pid + start identity in the shape the inline writers
#    parse, so a box-only copy and a helper-present writer see each other.
L="$T/shape.lock"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run test >/dev/null 2>&1 )
p="$(sed -n 's/^pid=\([0-9]*\).*/\1/p' "$L" 2>/dev/null | head -1)"
s="$(sed -n 's/^start=//p' "$L" 2>/dev/null | head -1)"
[ -n "$p" ] && [ -n "$s" ] && ok "the lease record carries pid and start identity in the shared shape" || bad "lease record shape unusable (pid='$p' start='$s')"

echo "=== Results: $pass passed, $fail failed ==="
[ "$fail" = 0 ]

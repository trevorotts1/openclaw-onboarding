#!/usr/bin/env bash
# tests/rescue/RRX-POLL/test_stale_lock_takeover.sh   (RRX-039)
#
# A lock left behind by a poll that is GONE used to be un-takeable forever: the
# generation was read with sed, which kept the JSON quotation marks, so the
# supervisor compared "123" with 123 and refused every takeover. The poll then
# exited 0 looking exactly like "another poll is running" — a silently dark box.
#
#   A  a dead owner's lock is taken over, one claim is made, the lock is gone
#   B  control: a lock whose owner is still ALIVE gives zero claims, no log line
#   C  an unreadable lock record is treated as no record; the poll takes the lock
#   D  a takeover that cannot read the record says so: zero claims, ONE
#      `lock-blocked reason=lock_record_unreadable` line across two runs
# Drives the real poll against a loopback stub. Offline, hermetic.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; REPO="$(cd "$HERE/../../.." && pwd)"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok   $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }
. "$HERE/../RR-030/lib-w4-poll-harness.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx039-stalelock-XXXXXX")"
SUP="$REPO/shared-utils/rescue-supervise.py"
REAL_PY="$(command -v python3)"
SLEEPS=""
cleanup() {
  w4_stop_receiver
  for _p in $SLEEPS; do kill "$_p" 2>/dev/null; done
  rm -rf "$WORK"
}
trap cleanup EXIT

# make_dead_owner_lock <box-root> <slug>
#   Starts a short-lived process, records the lock as ITS lock, then waits for
#   that process to end, so the incumbent is genuinely GONE.
make_dead_owner_lock() {
  local root="$1" slug="$2" pid=""
  sleep 3 & pid=$!
  SLEEPS="$SLEEPS $pid"
  python3 "$SUP" lock acquire --dir "$(w4_state "$root")/lock" \
    --owner-token old --owner-pid "$pid" --generation "$pid" \
    --target-kind box --resource-id "$slug" --target-key "box|$slug" \
    --lease-seconds 900 >/dev/null 2>&1
  local rc=$?
  wait "$pid" 2>/dev/null
  return $rc
}

log_count() { cat "$1" 2>/dev/null | grep -c "$2" 2>/dev/null || true; }

echo "== RRX-039: a lock left by a dead poll must be taken over =="

# ---- A: dead owner -> takeover, exactly one claim, lock released -------------
B="$WORK/a"; mkdir -p "$B"
w4_start_receiver "$B" 200 '{"status":"empty"}' || { bad "A receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-synthetic"
make_dead_owner_lock "$B" "box-synthetic"
[ -f "$(w4_state "$B")/lock/lock.json" ] && ok "A the dead owner's lock record exists before the run" \
  || bad "A lock record was not created"
w4_run_poll "$B"; ST="$(w4_state "$B")"
[ "$W4_RC" -eq 0 ] && ok "A0 poll exits 0 (cron contract unchanged)" || bad "A0 rc=$W4_RC"
[ "$(w4_claims "$B")" = "1" ] && ok "A1 the takeover produced exactly one claim" \
  || bad "A1 claim count" "$(w4_claims "$B")"
[ ! -f "$ST/lock/lock.json" ] && ok "A2 the lock is released after the run" \
  || bad "A2 lock.json still present"

# ---- B: control, live owner -> zero claims, no lock-blocked line -------------
B="$WORK/b"; mkdir -p "$B"
w4_start_receiver "$B" 200 '{"status":"empty"}' || { bad "B receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-synthetic"
sleep 30 & LIVE_PID=$!
SLEEPS="$SLEEPS $LIVE_PID"
python3 "$SUP" lock acquire --dir "$(w4_state "$B")/lock" \
  --owner-token live --owner-pid "$LIVE_PID" --generation "$LIVE_PID" \
  --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
  --lease-seconds 900 >/dev/null 2>&1
w4_run_poll "$B"; ST="$(w4_state "$B")"
[ "$W4_RC" -eq 0 ] && ok "B0 poll exits 0 while a live poll holds the lock" || bad "B0 rc=$W4_RC"
[ "$(w4_claims "$B")" = "0" ] && ok "B1 control: zero claims while the owner is alive" \
  || bad "B1 claim count" "$(w4_claims "$B")"
[ "$(log_count "$ST/rescue-poll.log" 'lock-blocked')" = "0" ] \
  && ok "B2 control: no lock-blocked line (contention is normal and quiet)" \
  || bad "B2 lock-blocked logged" "$(cat "$ST/rescue-poll.log" 2>/dev/null)"
kill "$LIVE_PID" 2>/dev/null; wait "$LIVE_PID" 2>/dev/null

# ---- C: unreadable record -> treated as no record, one claim -----------------
B="$WORK/c"; mkdir -p "$B"
w4_start_receiver "$B" 200 '{"status":"empty"}' || { bad "C receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-synthetic"
mkdir -p "$(w4_state "$B")/lock"
printf '%s' '{broken' > "$(w4_state "$B")/lock/lock.json"
w4_run_poll "$B"; ST="$(w4_state "$B")"
[ "$W4_RC" -eq 0 ] && ok "C0 poll exits 0 on an unreadable lock record" || bad "C0 rc=$W4_RC"
[ "$(w4_claims "$B")" = "1" ] && ok "C1 an unreadable record is no record: exactly one claim" \
  || bad "C1 claim count" "$(w4_claims "$B")"
[ "$(log_count "$ST/rescue-poll.log" 'lock-blocked')" = "0" ] \
  && ok "C2 no lock-blocked line (the poll simply took the lock)" \
  || bad "C2 lock-blocked logged" "$(cat "$ST/rescue-poll.log" 2>/dev/null)"

# ---- D: the record cannot be read during takeover -> say so, once ------------
B="$WORK/d"; mkdir -p "$B"
w4_start_receiver "$B" 200 '{"status":"empty"}' || { bad "D receiver stub did not start"; exit 1; }
w4_make_box "$B" "box-synthetic"
make_dead_owner_lock "$B" "box-synthetic"
# A python3 that fails ONLY when the supervisor is asked to inspect the record.
cat > "$B/bin/python3" <<STUB
#!/bin/sh
for _a in "\$@"; do [ "\$_a" = "inspect" ] && exit 1; done
exec "$REAL_PY" "\$@"
STUB
chmod +x "$B/bin/python3"
w4_run_poll "$B"; ST="$(w4_state "$B")"
w4_run_poll "$B"
[ "$W4_RC" -eq 0 ] && ok "D0 both runs exit 0" || bad "D0 rc=$W4_RC"
[ "$(w4_claims "$B")" = "0" ] && ok "D1 a takeover that cannot read the record makes zero claims" \
  || bad "D1 claim count" "$(w4_claims "$B")"
N="$(log_count "$ST/rescue-poll.log" 'lock-blocked reason=lock_record_unreadable')"
[ "$N" = "1" ] && ok "D2 exactly one lock-blocked reason=lock_record_unreadable line across two runs" \
  || bad "D2 lock-blocked line count" "$N :: $(cat "$ST/rescue-poll.log" 2>/dev/null)"

echo; echo "RRX-039 stale lock takeover: $PASS passed, $FAIL failed"; [ "$FAIL" -eq 0 ]

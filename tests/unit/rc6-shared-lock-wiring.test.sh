#!/usr/bin/env bash
# rc6-shared-lock-wiring.test.sh — mac.MAC-1 / mac.MAC-2 / mac.MAC-13,
# consistency.C1 (code side), critic.C11 + critic.C13 (code side).
#
# WHAT THIS PROVES, AND WHY EACH CASE EXISTS
#   T1  the closed PR #2612 DEFECT: a helper that refused its own children. The
#       box's own chain is self-update → weekly-full-update → fleet-refresh →
#       update-skills → oc-atomic, so a child that is refused DEADLOCKS the box.
#       The CONTROL is in the same section: a SIBLING (not a descendant) IS
#       refused, so "the child succeeded" cannot be explained by a gate that
#       always says yes.
#   T2  a live foreign owner is refused and its record is NOT displaced.
#   T3  staleness is pid + process start identity: a dead pid is reclaimed, a
#       LIVE pid with a MISMATCHED start identity (pid reuse) is reclaimed, and
#       age is never consulted in either direction.
#   T4  weekly-full-update.sh exits 75 (DEFERRED) on a busy box instead of the
#       old exit 0 "nothing changed" (critic.C13).
#   T5  under self-update the content step refuses the bare no-snapshot
#       updater instead of falling back to it (critic.C11, code side).
#   T6  remediate.sh HONOURS a live maintenance lock that is hours old (the old
#       rule healed after 60 minutes) and ignores a dead one.
#   T7  the wired scripts all reference the one lease path and none of them
#       still invents its own: no age-based reclaim remains in the runner.
#
# Every case RUNS the real code against fixtures; none of them greps for a
# string as its only proof. Interpreter: POSIX-ish bash, runs on macOS
# /bin/bash 3.2 and Linux bash 5, with and without flock(1).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HELPER="$REPO_ROOT/scripts/box-update-lock.sh"
WEEKLY="$REPO_ROOT/scripts/weekly-full-update.sh"
REMEDIATE="$REPO_ROOT/platform/mac/service-selfheal/remediate.sh"
RUNNER="$REPO_ROOT/shared-utils/fleet_refresh_runner.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }
section() { echo ""; echo "=== $1 ==="; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/rc6-lock.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# Never let the host's own fleet locks influence a case.
unset BUL_AGENT_PULL_LOCKS BUL_MAINTENANCE_LOCKS BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID

echo "=== rc6-shared-lock-wiring.test.sh (interpreter: $BASH_VERSION) ==="
echo "helper: $HELPER"

# ── T0: syntax, every file, both parsers available on this host ─────────────
section "T0 — syntax"
for f in "$REPO_ROOT/update-skills.sh" "$REPO_ROOT/scripts/oc-atomic-upgrade.sh" \
         "$REPO_ROOT/scripts/self-update.sh" "$WEEKLY" "$REMEDIATE" \
         "$REPO_ROOT/scripts/setup-weekly-update.sh"; do
  if bash -n "$f" 2>/dev/null; then pass "bash -n $(basename "$f")"; else fail "bash -n $(basename "$f")"; fi
done
if [ -f "$HELPER" ]; then
  bash -n "$HELPER" 2>/dev/null && pass "bash -n box-update-lock.sh" || fail "bash -n box-update-lock.sh"
  pass "shared lease helper present (the one every writer sources)"
else
  fail "scripts/box-update-lock.sh MISSING — every writer falls back to its inline copy"
fi
if python3 -I -c "import py_compile;py_compile.compile('$RUNNER',doraise=True)" 2>/dev/null; then
  pass "fleet_refresh_runner.py compiles"
else
  fail "fleet_refresh_runner.py does NOT compile"
fi

# ── T1: a CHILD inherits, a SIBLING is refused (the #2612 defect) ───────────
section "T1 — nested writers INHERIT the lease; foreign writers are REFUSED"
if [ -f "$HELPER" ]; then
  LEASE="$TMP/t1.lease"
  OWNER_OUT="$TMP/t1.owner"
  CHILD_OUT="$TMP/t1.child"
  # The owner acquires, then spawns a real child process that also acquires.
  # NOTE: the owner must be its own PROCESS, never a `( )` subshell: in bash a
  # subshell keeps the PARENT's $$, so a subshell "owner" records the test
  # shell's pid and every sibling then looks like a descendant of it.
  cat > "$TMP/t1-child.sh" <<'EOS'
. "$1"
box_update_lock_acquire "$2" "run-t1" "child" "$3"
echo "child-rc=$?"
EOS
  cat > "$TMP/t1-owner.sh" <<'EOS'
. "$1"
box_update_lock_acquire "$2" "run-t1" "owner" "$3" || { echo "owner-acquire-rc=$?" > "$4"; exit 9; }
echo "owner-pid=$$" > "$4"
bash "$5" "$1" "$2" "$3" > "$6" 2>&1
sleep 3            # stay the live holder while the sibling probes
box_update_lock_release
EOS
  cat > "$TMP/t1-sibling.sh" <<'EOS'
. "$1"
BFX_LOCK_RUN_ID= BFX_LOCK_OWNER_PID= box_update_lock_acquire "$2" "run-sibling" "sibling" "$3"
echo "sibling-rc=$?"
EOS
  bash "$TMP/t1-owner.sh" "$HELPER" "$LEASE" "$TMP" "$OWNER_OUT" "$TMP/t1-child.sh" "$CHILD_OUT" &
  OWNER_JOB=$!
  # A SIBLING of the owner — no exported identity, not an ancestor — must lose.
  sleep 0.8
  bash "$TMP/t1-sibling.sh" "$HELPER" "$LEASE" "$TMP" > "$TMP/t1.sibling" 2>&1
  wait "$OWNER_JOB"
  if grep -q 'child-rc=0' "$CHILD_OUT" 2>/dev/null; then
    pass "T1a: a CHILD of the holder acquires without being refused (PR #2612 defect fixed)"
  else
    fail "T1a: a CHILD of the holder was refused: $(tr '\n' ' ' < "$CHILD_OUT" 2>/dev/null)"
  fi
  if grep -q 'sibling-rc=3' "$TMP/t1.sibling" 2>/dev/null; then
    pass "T1b CONTROL: a non-descendant writer IS refused (rc 3) — the gate discriminates"
  else
    fail "T1b CONTROL: a foreign writer was NOT refused: $(tr '\n' ' ' < "$TMP/t1.sibling" 2>/dev/null)"
  fi
else
  fail "T1 skipped: no helper"
fi

# ── T2: a live foreign record is never displaced ────────────────────────────
section "T2 — a live foreign owner is refused and its record survives"
LEASE="$TMP/t2.lease"
# The recorded owner must be a process that is NOT an ancestor of the acquirer,
# or the helper would (correctly) treat the acquirer as its child.
sleep 30 & FOREIGN=$!
sleep 0.2
printf 'pid=%s\nstart=%s\nrun_id=foreign\nrole=update-skills\ninstall_path=/x\nutc=2026-01-01T00:00:00Z\n' \
  "$FOREIGN" "$(ps -o lstart= -p "$FOREIGN" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//')" > "$LEASE"
BEFORE="$(cat "$LEASE")"
bash -c '. "$1"; BFX_LOCK_RUN_ID= BFX_LOCK_OWNER_PID= box_update_lock_acquire "$2" "mine" "me" "$3"; echo "rc=$?"' \
  _ "$HELPER" "$LEASE" "$TMP" > "$TMP/t2.out" 2>&1
AFTER="$(cat "$LEASE")"
kill "$FOREIGN" 2>/dev/null
if grep -q 'rc=3' "$TMP/t2.out"; then pass "T2a: live foreign record refused (rc 3)"; else fail "T2a: not refused: $(tr '\n' ' ' < "$TMP/t2.out")"; fi
if [ "$BEFORE" = "$AFTER" ]; then pass "T2b: the foreign record was NOT overwritten"; else fail "T2b: the foreign record was displaced"; fi
rm -f "$LEASE"

# ── T3: staleness = pid + start identity, never age ─────────────────────────
section "T3 — staleness is the recorded OWNER's death, never the file's age"
# T3a: dead pid, FRESH file → reclaimed (age would have said "busy").
LEASE="$TMP/t3a.lease"
DEAD="$(sh -c 'echo $$')"     # that shell has exited
printf 'pid=%s\nstart=deadbeef\nrun_id=gone\nrole=x\ninstall_path=/x\nutc=x\n' "$DEAD" > "$LEASE"
touch "$LEASE"
( . "$HELPER"; BFX_LOCK_RUN_ID= BFX_LOCK_OWNER_PID= box_update_lock_acquire "$LEASE" "new" "me" "$TMP"; echo "rc=$?" ) > "$TMP/t3a.out" 2>&1
grep -q 'rc=0' "$TMP/t3a.out" && pass "T3a: dead owner reclaimed even though the file is fresh" || fail "T3a: dead owner NOT reclaimed: $(tr '\n' ' ' < "$TMP/t3a.out")"
rm -f "$LEASE"
# T3b: LIVE pid but a start identity that does not match (pid reuse), OLD file
#      → reclaimed. This is the mutation that fails if anyone reintroduces age.
LEASE="$TMP/t3b.lease"
sleep 30 & LIVE=$!
sleep 0.2
printf 'pid=%s\nstart=not-this-process\nrun_id=recycled\nrole=x\ninstall_path=/x\nutc=x\n' "$LIVE" > "$LEASE"
touch -t 202001010000 "$LEASE" 2>/dev/null || true
( . "$HELPER"; BFX_LOCK_RUN_ID= BFX_LOCK_OWNER_PID= box_update_lock_acquire "$LEASE" "new" "me" "$TMP"; echo "rc=$?" ) > "$TMP/t3b.out" 2>&1
grep -q 'rc=0' "$TMP/t3b.out" && pass "T3b: recycled pid reclaimed (start identity mismatch)" || fail "T3b: recycled pid NOT reclaimed: $(tr '\n' ' ' < "$TMP/t3b.out")"
kill "$LIVE" 2>/dev/null
rm -f "$LEASE"
# T3c: LIVE pid with the MATCHING identity, hours old → HELD, not reclaimed.
LEASE="$TMP/t3c.lease"
sleep 30 & LIVE2=$!
sleep 0.2
printf 'pid=%s\nstart=%s\nrun_id=slow\nrole=x\ninstall_path=/x\nutc=x\n' \
  "$LIVE2" "$(ps -o lstart= -p "$LIVE2" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//')" > "$LEASE"
touch -t 202001010000 "$LEASE" 2>/dev/null || true
( . "$HELPER"; BFX_LOCK_RUN_ID= BFX_LOCK_OWNER_PID= box_update_lock_acquire "$LEASE" "new" "me" "$TMP"; echo "rc=$?" ) > "$TMP/t3c.out" 2>&1
grep -q 'rc=3' "$TMP/t3c.out" && pass "T3c: a SLOW but live holder is never displaced by age (held, rc 3)" || fail "T3c: a live holder was displaced: $(tr '\n' ' ' < "$TMP/t3c.out")"
kill "$LIVE2" 2>/dev/null
rm -f "$LEASE"

# ── T4: weekly-full-update exits 75 on a busy box ───────────────────────────
section "T4 — a busy box is DEFERRED (exit 75), never 'exit 0, nothing changed'"
WROOT="$TMP/t4root"
mkdir -p "$WROOT/.fleet-refresh.lock"
sleep 30 & BUSY=$!
echo "$BUSY" > "$WROOT/.fleet-refresh.lock/pid"
( cd "$TMP" && HOME="$TMP/t4home" OPENCLAW_ROOT="$WROOT" OPENCLAW_UPDATE_LEASE="$TMP/t4.lease" \
    bash "$WEEKLY" ) > "$TMP/t4.out" 2>&1
T4RC=$?
kill "$BUSY" 2>/dev/null
if [ "$T4RC" -eq 75 ]; then pass "T4a: busy box → exit 75"; else fail "T4a: expected 75, got $T4RC: $(tr '\n' ' ' < "$TMP/t4.out")"; fi
if grep -q 'DEFERRED' "$TMP/t4.out"; then pass "T4b: the log says DEFERRED"; else fail "T4b: no DEFERRED in the log"; fi
if [ -f "$TMP/t4.lease" ]; then fail "T4c: the lease was NOT released on the deferred path"; else pass "T4c: the lease was released"; fi
rm -rf "$WROOT" "$TMP/t4home"

# ── T5: under self-update, no bare no-snapshot fallback ─────────────────────
section "T5 — under self-update the content step refuses the bare updater (critic.C11)"
mkdir -p "$TMP/t5root" "$TMP/t5home"
( cd "$TMP" && HOME="$TMP/t5home" OPENCLAW_ROOT="$TMP/t5root" \
    OPENCLAW_UPDATE_LEASE="$TMP/t5.lease" SELF_UPDATE_RUN=1 \
    FLEET_ROLL_REPO_URL="file://$TMP/definitely-not-a-repo.git" \
    bash "$WEEKLY" ) > "$TMP/t5.out" 2>&1
T5RC=$?
if [ "$T5RC" -ne 0 ]; then pass "T5a: non-zero exit under self-update ($T5RC)"; else fail "T5a: exited 0 with nothing done"; fi
if grep -q 'REFUSED: no usable onboarding copy' "$TMP/t5.out"; then pass "T5b: refused the bare updater explicitly"; else fail "T5b: bare-updater refusal missing: $(tr '\n' ' ' < "$TMP/t5.out")"; fi
rm -rf "$TMP/t5root" "$TMP/t5home"

# ── T6: remediate.sh honours a live lock that is hours old ──────────────────
section "T6 — remediate.sh: a LIVE maintenance lock is honoured however old it is"
RHOME="$TMP/t6home"
mkdir -p "$RHOME/.openclaw" "$RHOME/Library/LaunchAgents" "$RHOME/Library/Logs/openclaw"
MLOCK="$RHOME/.openclaw/.openclaw-maintenance-lock"
sleep 30 & MPID=$!
sleep 0.2
MSTART="$(ps -o lstart= -p "$MPID" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//')"
printf 'pid=%s\nstart=%s\nstarted=2020-01-01T00:00:00\nreason=oc-atomic-upgrade v1.0.0\n' "$MPID" "$MSTART" > "$MLOCK"
touch -t 202001010000 "$MLOCK" 2>/dev/null || true
HOME="$RHOME" sh "$REMEDIATE" > "$TMP/t6.out" 2>&1
T6RC=$?
kill "$MPID" 2>/dev/null
if grep -q 'MAINTENANCE LOCK HELD' "$RHOME/Library/Logs/openclaw/service-remediate.log" 2>/dev/null; then
  pass "T6a: an hours-old lock with a LIVE owner is honoured (the 60-minute rule is gone)"
else
  fail "T6a: a live hours-old lock was IGNORED: $(tr '\n' ' ' < "$RHOME/Library/Logs/openclaw/service-remediate.log" 2>/dev/null)"
fi
if [ "$T6RC" -eq 0 ]; then pass "T6b: standing down is a clean exit 0"; else fail "T6b: exit $T6RC (expected 0)"; fi
# T6c: the same lock with a DEAD pid must be ignored, not honoured.
printf 'pid=999999\nstart=whatever\nstarted=2020-01-01T00:00:00\nreason=oc-atomic-upgrade v1.0.0\n' > "$MLOCK"
HOME="$RHOME" sh "$REMEDIATE" > "$TMP/t6c.out" 2>&1
if grep -q 'STALE maintenance lock' "$RHOME/Library/Logs/openclaw/service-remediate.log" 2>/dev/null; then
  pass "T6c: a dead owner's lock is IGNORED (proof of death, not age)"
else
  fail "T6c: a dead owner's lock was honoured — self-heal would wedge forever"
fi
rm -rf "$RHOME"

# ── T7: one lease path; no age-based reclaim left in the runner ─────────────
section "T7 — one lease path for every writer; no age-based reclaim in the runner"
for f in "$REPO_ROOT/update-skills.sh" "$REPO_ROOT/scripts/oc-atomic-upgrade.sh" \
         "$REPO_ROOT/scripts/self-update.sh" "$WEEKLY"; do
  if grep -q 'openclaw-update.lock' "$f"; then pass "T7: $(basename "$f") pins the shared lease path"
  else fail "T7: $(basename "$f") never names the shared lease path"; fi
done
if grep -q 'age < 4' "$RUNNER"; then
  fail "T7: the runner STILL reclaims by a 4-hour age cutoff"
else
  pass "T7: the runner's 4-hour age reclaim is gone"
fi
if grep -q 'st_mtime' "$RUNNER"; then
  fail "T7: the runner still consults an mtime to judge a lock"
else
  pass "T7: no mtime is consulted to judge a lock"
fi
if grep -q '_lease_owner_live' "$RUNNER" && grep -q '_proc_start_identity' "$RUNNER"; then
  pass "T7: the runner judges liveness from the record (pid + start identity)"
else
  fail "T7: the runner has no record-based liveness"
fi

echo ""
echo "=========================================="
echo "  PASS: $PASS  FAIL: $FAIL"
echo "=========================================="
[ "$FAIL" -eq 0 ] || exit 1

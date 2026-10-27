#!/usr/bin/env bash
# Contract test: one box, one update owner — scripts/box-update-lock.sh
#
# No framework: assert-based, exits non-zero on any failed assertion.
# Covers: live owner refused / dead owner reclaimed / pid reuse not an owner /
# child + grandchild inherit / non-owner release keeps the lease / legacy
# directory lease / foreign writers (NB9) / fixed flock fd on bash 3.2 (MAC-8) /
# a negative control against the closed PR #2612 helper (which refused its own
# child) and against its `exec {FD}>` construct.
#
# Run: bash tests/unit/box-update-lock.test.sh
#      /bin/bash tests/unit/box-update-lock.test.sh     (macOS 3.2)

set -u
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
LOCK_SH="$HERE/../../scripts/box-update-lock.sh"
pass=0
fail=0
ok() { pass=$((pass + 1)); printf '  PASS: %s\n' "$1"; }
bad() { fail=$((fail + 1)); printf '  FAIL: %s\n' "$1"; }

[ -f "$LOCK_SH" ] || { printf 'FATAL: missing %s\n' "$LOCK_SH"; exit 1; }

T="$(mktemp -d)" || exit 1
SLEEPER=""
cleanup() {
  if [ -n "$SLEEPER" ]; then
    kill "$SLEEPER" 2>/dev/null
    wait "$SLEEPER" 2>/dev/null
  fi
  rm -rf "$T"
}
trap cleanup EXIT

# Hermetic: never let a real box lock on this machine decide a test.
export BUL_AGENT_PULL_LOCKS=""
export BUL_MAINTENANCE_LOCKS=""
export BUL_MAINTENANCE_FRESH_MINUTES=60
unset BFX_LOCK_RUN_ID BFX_LOCK_OWNER_PID 2>/dev/null || true

start_of() { ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//'; }
rec() { sed -n "s/^$1=//p" "$2" 2>/dev/null | head -1; }

# acq <lock> <run> <role> -> rc
acq() {
  ( . "$LOCK_SH"; box_update_lock_acquire "$1" "$2" "$3" >/dev/null 2>&1; exit $? )
}
# rel <lock> -> rc (in a throwaway process: never the owner)
rel() {
  ( . "$LOCK_SH"; BUL_LOCK_PATH="$1"; box_update_lock_release >/dev/null 2>&1; exit $? )
}

sleep 300 &
SLEEPER=$!
S="$(start_of "$SLEEPER")"
[ -n "$S" ] || { printf 'FATAL: cannot read a process start identity\n'; exit 1; }

printf '== box-update-lock under %s (%s)\n' "${BASH_VERSION:-unknown}" "${BASH:-unknown}"

# 1. A live recorded owner is never displaced.
L="$T/live.lock"
printf 'pid=%s\nstart=%s\nrun_id=holder\nrole=test\n' "$SLEEPER" "$S" >"$L"
acq "$L" run test
rc=$?
[ "$rc" = 3 ] && ok "a LIVE recorded owner means REFUSE (rc=3)" || bad "live owner not refused (rc=$rc)"
[ "$(rec pid "$L")" = "$SLEEPER" ] && ok "a refused writer leaves the owner record untouched" \
  || bad "a refused writer overwrote the owner record"

# 2. A dead owner is reclaimed, with a REAL start identity (not a fake one).
DEADPID="$( (sleep 0.05 & echo $!) )"
DPSTART="$(start_of "$DEADPID")"
sleep 0.3
L="$T/dead.lock"
printf 'pid=%s\nstart=%s\nrun_id=dead\nrole=test\n' "$DEADPID" "$DPSTART" >"$L"
acq "$L" run test
rc=$?
[ "$rc" = 0 ] && ok "a DEAD recorded owner (real start identity) is reclaimed (rc=0)" \
  || bad "dead lease not reclaimed (rc=$rc)"

# 3. pid reuse: same pid, different start identity, is not the owner.
L="$T/reuse.lock"
printf 'pid=%s\nstart=not-this-process\nrun_id=x\nrole=test\n' "$SLEEPER" >"$L"
acq "$L" run test
rc=$?
[ "$rc" = 0 ] && ok "a reused pid with a different start identity is not a live owner (rc=0)" \
  || bad "pid-reuse guard failed (rc=$rc)"

# 4. A record with no start identity at all is not proof of life (partial write).
L="$T/nostart.lock"
printf 'pid=%s\nrun_id=x\nrole=test\n' "$SLEEPER" >"$L"
acq "$L" run test
rc=$?
[ "$rc" = 0 ] && ok "a record without a start identity is not treated as live (rc=0)" \
  || bad "start-less record accepted as a live owner (rc=$rc)"

# 5. The owner's release removes the lease; a non-owner's release does not.
L="$T/mine.lock"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run test >/dev/null 2>&1; box_update_lock_release )
[ -f "$L" ] && bad "the owner's release left the lease" || ok "the owner's release removes the lease"

L="$T/notmine.lock"
printf 'pid=%s\nstart=%s\nrun_id=other\nrole=test\n' "$SLEEPER" "$S" >"$L"
rel "$L"
[ -f "$L" ] && ok "a non-owner release leaves the lease in place" \
  || bad "non-owner release deleted the lease"

# 6. The record carries every field the contract names, in the shared shape.
L="$T/shape.lock"
( . "$LOCK_SH"; box_update_lock_acquire "$L" run-9 "self-update" "/opt/openclaw" >/dev/null 2>&1 )
[ -n "$(rec pid "$L")" ] && [ -n "$(rec start "$L")" ] && [ "$(rec run_id "$L")" = "run-9" ] &&
  [ "$(rec role "$L")" = "self-update" ] && [ "$(rec install_path "$L")" = "/opt/openclaw" ] &&
  [ -n "$(rec utc "$L")" ] &&
  ok "the lease record carries pid, start, run_id, role, install_path and utc" ||
  bad "lease record incomplete: $(tr '\n' ' ' <"$L" 2>/dev/null)"

# 7. A child of the owner proceeds WITHOUT re-acquiring (the PR #2612 deadlock).
#    The record must still name the OWNER, and the child must be rc 0.
L="$T/child.lock"
child_case() {
  ( . "$LOCK_SH"
    box_update_lock_acquire "$1" "run-child" "self-update" >/dev/null 2>&1 || exit 9
    before="$(sed -n 's/^pid=//p' "$1" | head -1)"
    bash -c '. "$1"; box_update_lock_acquire "$2" "run-child" "self-update" >/dev/null 2>&1; exit $?' \
      _ "$LOCK_SH" "$1"
    crc=$?
    bash -c 'bash -c ". \"\$1\"; box_update_lock_acquire \"\$2\" \"run-child\" \"self-update\" >/dev/null 2>&1; exit \$?" _ "$1" "$2"' \
      _ "$LOCK_SH" "$1"
    grc=$?
    after="$(sed -n 's/^pid=//p' "$1" | head -1)"
    [ "$crc" = 0 ] || exit 20
    [ "$grc" = 0 ] || exit 21
    [ "$before" = "$after" ] || exit 22
    exit 0 )
}
child_case "$L"
rc=$?
[ "$rc" = 0 ] && ok "a CHILD and GRANDCHILD of the owner inherit the lease without re-acquiring (rc=0, record unchanged)" \
  || bad "child inheritance failed (rc=$rc; 20=child refused, 21=grandchild refused, 22=record rewritten)"
[ -f "$L" ] && ok "an inheriting child's exit leaves the owner's lease in place" \
  || bad "an inheriting child deleted the owner's lease"

# 8. Same env, but the record is owned by a LIVE process that is NOT an ancestor:
#    inheritance must not be granted (proves the ancestor check is real).
L="$T/notancestor.lock"
printf 'pid=%s\nstart=%s\nrun_id=run-x\nrole=test\n' "$SLEEPER" "$S" >"$L"
( export BFX_LOCK_RUN_ID=run-x BFX_LOCK_OWNER_PID="$SLEEPER"
  . "$LOCK_SH"; box_update_lock_acquire "$L" run-x test >/dev/null 2>&1; exit $? )
rc=$?
[ "$rc" = 3 ] && ok "a matching run id held by a live NON-ancestor still REFUSES (rc=3)" \
  || bad "inheritance granted without an ancestor (rc=$rc)"

# 9. The owner died leaving the same run's env: the orphaned child adopts it.
L="$T/adopt.lock"
printf 'pid=999999\nstart=gone\nrun_id=run-y\nrole=test\n' >"$L"
( export BFX_LOCK_RUN_ID=run-y BFX_LOCK_OWNER_PID=999999
  . "$LOCK_SH"; box_update_lock_acquire "$L" run-y test >/dev/null 2>&1; exit $? )
rc=$?
[ "$rc" = 0 ] && ok "the same run adopts a DEAD lease instead of being refused (rc=0)" \
  || bad "dead-lease adoption failed (rc=$rc)"
[ -n "$(rec pid "$L")" ] && [ "$(rec pid "$L")" != "999999" ] &&
  ok "the adopted lease names the adopting process" || bad "adopted lease still names the dead pid"

# 10. A legacy DIRECTORY lease (main's mkdir fallback) with a live pid refuses.
L="$T/dir.lock"
mkdir -p "$L"
printf '%s\n' "$SLEEPER" >"$L/pid"
acq "$L" run test
rc=$?
[ "$rc" = 3 ] && ok "a legacy DIRECTORY lease with a live pid REFUSES the acquire (rc=3)" \
  || bad "live directory lease accepted (rc=$rc)"

# 11. ... and with a dead pid it is reclaimed.
L="$T/dir-dead.lock"
mkdir -p "$L"
printf '999999\n' >"$L/pid"
acq "$L" run test
rc=$?
[ "$rc" = 0 ] && [ -f "$L" ] &&
  ok "a legacy DIRECTORY lease with a dead pid is reclaimed as a regular record (rc=0)" ||
  bad "dead directory lease not reclaimed (rc=$rc)"

# 12. neverBroken.NB9: a live agent-pull job refuses the acquire.
export BUL_AGENT_PULL_LOCKS="$T/ap/agent-pull.lock"
mkdir -p "$T/ap/agent-pull.lock"
printf '%s\n' "$SLEEPER" >"$T/ap/agent-pull.lock/pid"
L="$T/nb9a.lock"
acq "$L" run test
rc=$?
[ "$rc" = 3 ] && ok "a LIVE agent-pull.lock pid refuses the acquire (rc=3)" \
  || bad "live agent-pull lock not honoured (rc=$rc)"
[ -f "$L" ] && bad "a foreign-lock refusal still created the lease" || ok "a foreign-lock refusal writes no lease"

# 13. ... and a dead agent-pull pid does not.
printf '999999\n' >"$T/ap/agent-pull.lock/pid"
acq "$L" run test
rc=$?
[ "$rc" = 0 ] && ok "a DEAD agent-pull pid does not block the acquire (rc=0)" \
  || bad "dead agent-pull pid blocked the acquire (rc=$rc)"
export BUL_AGENT_PULL_LOCKS=""

# 14. neverBroken.NB9: a fresh .openclaw-maintenance-lock refuses; an old one does not.
export BUL_MAINTENANCE_LOCKS="$T/maint.lock"
printf 'reason=oc-atomic-upgrade v9\n' >"$T/maint.lock"
L="$T/nb9b.lock"
acq "$L" run test
rc=$?
[ "$rc" = 3 ] && ok "a FRESH .openclaw-maintenance-lock refuses the acquire (rc=3)" \
  || bad "fresh maintenance lock not honoured (rc=$rc)"
touch -t 202001010000 "$T/maint.lock"
acq "$L" run test
rc=$?
[ "$rc" = 0 ] && ok "an OLD .openclaw-maintenance-lock does not block the acquire (rc=0)" \
  || bad "old maintenance lock blocked the acquire (rc=$rc)"
export BUL_MAINTENANCE_LOCKS=""

# 15. mac.MAC-8: flock path uses a FIXED fd, so macOS /bin/bash 3.2 survives.
mkdir -p "$T/bin"
cat >"$T/bin/flock" <<'FAKE'
#!/bin/sh
# Fake flock: exercises the helper's fd protocol without a real lock daemon.
case "$1" in
  -n) [ -e "${FAKE_FLOCK_MARK}" ] && exit 1
      : >"${FAKE_FLOCK_MARK}" 2>/dev/null
      printf '%s %s\n' "$1" "$2" >>"${FAKE_FLOCK_LOG}" 2>/dev/null
      exit 0 ;;
  -u) rm -f "${FAKE_FLOCK_MARK}" 2>/dev/null; printf '%s %s\n' "$1" "$2" >>"${FAKE_FLOCK_LOG}" 2>/dev/null; exit 0 ;;
esac
exit 0
FAKE
chmod +x "$T/bin/flock"
export FAKE_FLOCK_MARK="$T/flock.mark"
export FAKE_FLOCK_LOG="$T/flock.log"
L="$T/flock.lock"
( PATH="$T/bin:$PATH"; BUL_SKIP_FOREIGN_GATE=1
  /bin/bash -c '. "$1"; box_update_lock_acquire "$2" run-f role-f >/dev/null 2>&1; exit $?' _ "$LOCK_SH" "$L" )
rc=$?
[ "$rc" = 0 ] && ok "the flock path acquires under /bin/bash 3.2 (rc=0, not 127)" \
  || bad "flock path under bash 3.2 returned rc=$rc"
grep -qx -- '-n 9' "$FAKE_FLOCK_LOG" 2>/dev/null &&
  ok "the flock guard was taken on the FIXED fd 9, not a {brace} variable" ||
  bad "flock did not receive a fixed fd 9: $(tr '\n' ' ' <"$FAKE_FLOCK_LOG" 2>/dev/null)"
: >"$T/flock.log"
: >"$FAKE_FLOCK_MARK" # simulate another holder on the flock
( PATH="$T/bin:$PATH"; BUL_SKIP_FOREIGN_GATE=1
  /bin/bash -c '. "$1"; box_update_lock_acquire "$2" run-f role-f >/dev/null 2>&1; exit $?' _ "$LOCK_SH" "$T/flock2.lock" )
rc=$?
[ "$rc" = 3 ] && ok "a held flock refuses with rc=3 (not a crash, not a silent proceed)" \
  || bad "held flock returned rc=$rc"
rm -f "$FAKE_FLOCK_MARK"
unset FAKE_FLOCK_MARK FAKE_FLOCK_LOG

# 16. NEGATIVE CONTROL — the closed PR #2612 helper REFUSES ITS OWN CHILD, which
#     is exactly the deadlock this unit exists to remove. If this control ever
#     passes as "inherited", the suite above is no longer discriminating.
cat >"$T/legacy-box-update-lock.sh" <<'LEGACY'
# Faithful trim of origin/batch/big-fleet-fix-lane:scripts/box-update-lock.sh
# (PR #2612, closed unmerged): record-based liveness, NO child inheritance.
_bul_start_identity() { ps -o lstart= -p "$1" 2>/dev/null | tr -s ' ' | sed 's/^ *//;s/ *$//'; }
_bul_owner_is_live() {
  local pid start now_start
  [ -f "$BUL_LOCK_PATH" ] || return 1
  pid="$(sed -n 's/^pid=\([0-9]*\).*/\1/p' "$BUL_LOCK_PATH" 2>/dev/null | head -1)"
  start="$(sed -n 's/^start=//p' "$BUL_LOCK_PATH" 2>/dev/null | head -1)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  if [ -n "$start" ]; then now_start="$(_bul_start_identity "$pid")"; [ "$now_start" = "$start" ] || return 1; fi
  return 0
}
_bul_write_owner() {
  { printf 'pid=%s\n' "$$"; printf 'start=%s\n' "$(_bul_start_identity $$)"
    printf 'run_id=%s\n' "${1:-}"; printf 'role=%s\n' "${2:-}"; } >"$BUL_LOCK_PATH"
}
box_update_lock_acquire() {
  BUL_LOCK_PATH="${1:-/tmp/openclaw-update.lock}"
  if _bul_owner_is_live; then return 3; fi
  [ -f "$BUL_LOCK_PATH" ] && rm -f "$BUL_LOCK_PATH"
  ( set -o noclobber; : >"$BUL_LOCK_PATH" ) 2>/dev/null || return 3
  _bul_write_owner "${2:-}" "${3:-}"
  return 0
}
LEGACY
L="$T/legacy.lock"
legacy_case() {
  ( . "$T/legacy-box-update-lock.sh"
    box_update_lock_acquire "$1" run-legacy parent || exit 9
    bash -c '. "$1"; box_update_lock_acquire "$2" run-legacy child; exit $?' _ "$T/legacy-box-update-lock.sh" "$1" )
}
legacy_case "$L"
rc=$?
[ "$rc" = 3 ] && ok "NEGATIVE CONTROL: the old PR #2612 helper REFUSES its own child (rc=3) — the suite discriminates" \
  || bad "negative control did not reproduce the old deadlock (rc=$rc)"

# 17. NEGATIVE CONTROL — the old `exec {FD}>` construct is rc 127 on bash 3.2.
/bin/bash -c 'exec {MYFD}>"$1"; echo reached' _ "$T/fdtest" >/dev/null 2>&1
rc=$?
[ "$rc" = 127 ] && ok "NEGATIVE CONTROL: exec {FD}> aborts with rc 127 on /bin/bash 3.2 (MAC-8 premise holds)" \
  || bad "expected rc 127 from exec {FD}> on 3.2, got rc=$rc"

# 18. The helper behaves under `set -euo pipefail`, which is how callers run it.
L="$T/strict.lock"
( set -euo pipefail
  . "$LOCK_SH"
  box_update_lock_acquire "$L" run-s role-s >/dev/null 2>&1
  box_update_lock_release
  [ -f "$L" ] && exit 1
  exit 0 )
rc=$?
[ "$rc" = 0 ] && ok "acquire + release succeed under set -euo pipefail, and release cleans up" \
  || bad "strict-mode acquire/release failed (rc=$rc)"

L="$T/strict-refuse.lock"
printf 'pid=%s\nstart=%s\nrun_id=holder\n' "$SLEEPER" "$S" >"$L"
( set -euo pipefail
  . "$LOCK_SH"
  if box_update_lock_acquire "$L" run role >/dev/null 2>&1; then exit 1; fi
  exit 0 )
rc=$?
[ "$rc" = 0 ] && ok "a refusal is a RETURN CODE under set -e: the caller can keep going" \
  || bad "strict-mode refusal aborted the caller (rc=$rc)"

# 19. The whole suite runs under the other interpreters (3.2 forced, 5 if present).
if [ "${BFX_TEST_NO_NEST-}" != "1" ]; then
  for B in /bin/bash /opt/homebrew/bin/bash /usr/local/bin/bash; do
    [ -x "$B" ] || continue
    [ "$B" = "${BASH:-}" ] && continue
    BFX_TEST_NO_NEST=1 "$B" "$0" >"$T/nested.log" 2>&1
    rc=$?
    [ "$rc" = 0 ] && ok "the suite passes under $B ($("$B" -c 'echo $BASH_VERSION'))" \
      || { bad "the suite FAILS under $B (rc=$rc)"; sed 's/^/        /' "$T/nested.log" | tail -5; }
  done
fi

printf '=== Results: %s passed, %s failed ===\n' "$pass" "$fail"
[ "$fail" = 0 ]

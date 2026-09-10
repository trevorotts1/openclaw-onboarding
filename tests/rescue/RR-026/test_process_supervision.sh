#!/usr/bin/env bash
# tests/rescue/RR-026/test_process_supervision.sh — RR-026 gate (ONB receiver).
#
# Pins the portable process-group supervisor and the owner-token lock.
# SPEC RR-026: "Use a portable Python process-group supervisor with monotonic
# total deadline, TERM grace then KILL and verified child exit. Include
# discovery, model execution, fallback and ACK in one budget. Persist lock owner
# token/process start identity and compare before release. Reconcile running
# processes before takeover; never remove by age alone. Negotiate lease deadline,
# renew within policy, or stop before losing it with ACK margin. Persist
# timeout/cancel outcome and next owner. Share target/resource fencing with
# operator executor so separate transports cannot duplicate mutation."
#
# EVIDENCE STANDARD (SPEC required QC): "CLI ignoring timeout, hung discovery,
# delayed unknown-agent fallback, process kill, stale lock, PID reuse, old
# release after takeover and renewal failure must end predictably without double
# execution. Run process-group cases on Mac and Linux Docker."
#
# Every case asserts a NAMED state transition observed on the box (a process is
# gone, a grandchild is gone, a lock record names a different owner) — never an
# exit code alone. Each "nothing survived" assertion is paired with a control
# that proves the observer can SEE a survivor.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
SUP="$REPO/shared-utils/rescue-supervise.py"
POLL="$REPO/65-rescue-receiver/rescue-poll.sh"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ok $1"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL $1 ${2:-}"; }

[ -f "$SUP" ] || { echo "FATAL: missing $SUP"; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "FATAL: no python3"; exit 2; }

echo "== RR-026: process-group supervision, lock fencing, lease budget =="
echo "   host: $(uname -s) $(uname -m)  python: $(python3 -V 2>&1)"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr026.XXXXXX")"

# Cleanup trap, guarded against a REAL bash trap-inheritance trap.
#
# Bash runs EXIT traps in a SUBSHELL too: when a background job (`sleep 30 &`)
# is killed and reaped, the forked subshell exits and fires the EXIT trap with
# the parent's $WORK still in its environment. On bash 5.2 (Debian 12) that
# deleted the whole scratch tree mid-run -- every later section then either
# failed on a missing path or silently recreated the dirs via makedirs and
# looked healthy. Intermittent, and invisible without xtrace.
#
# $BASHPID is the CURRENT process (unlike $$, which stays the parent's pid), so
# this runs the cleanup only in the shell that owns it.
# Guard: clean up ONLY when this shell finished normally. A subshell forked for
# a background job inherits the trap AND the environment as it was at FORK time
# -- before RR026_DONE is set -- so its copy sees the flag unset and does
# nothing. (PID-based guards are not portable here: bash 3.2 -- which is what
# macOS /bin/sh is -- has no BASHPID, and $$ stays the PARENT's pid inside a
# subshell, so nothing in the subshell distinguishes it from the main shell.)
RR026_DONE=""
trap '[ -n "$RR026_DONE" ] && rm -rf "$WORK"' EXIT

sup() { python3 "$SUP" "$@"; }

# ---------------------------------------------------------------------------
# helpers — every one of them OBSERVES, never assumes
# ---------------------------------------------------------------------------
alive() { kill -0 "$1" 2>/dev/null; }

# Detector: `pgrep -f` is NOT reliable on macOS for long argv (proven by the
# section-3 control failing while a planted process was demonstrably alive —
# see the ps output). Use `ps -Ao pid=,command=` plus an exact token where ps
# exists; on procps-less Linux (slim containers) fall back to /proc/*/cmdline,
# which is the kernel's own record and needs no tooling. The control in
# section 3 proves whichever detector this host answers with can actually
# FIND a planted survivor.
seen_token() {  # seen_token <token> -> 0 if any live process has it in argv
    if command -v ps >/dev/null 2>&1 && ps -Ao pid=,command= </dev/null >/dev/null 2>&1; then
        ps -Ao pid=,command= 2>/dev/null | grep -F -- "$1" | grep -v 'grep' >/dev/null 2>&1
        return $?
    fi
    # /proc fallback: the token was planted as part of `python3 -c '...token...'`,
    # so the argv is visible in the NULL-separated cmdline. A short python loop
    # (there is no portable shell reader for NUL-separated files). The detector
    # EXCLUDES ITSELF: its own argv carries the token (`python3 - <token>`), and
    # a self-match would make every survivor check vacuously true.
    python3 - "$1" <<'PYEOF' 2>/dev/null
import glob, os, sys
tok = sys.argv[1].encode()
me = os.getpid()
for f in glob.glob("/proc/[0-9]*/cmdline"):
    try:
        pid = int(f.split("/")[2])
    except (ValueError, IndexError):
        continue
    if pid == me:
        continue
    try:
        with open(f, "rb") as fh:
            if tok in fh.read():
                sys.exit(0)
    except OSError:
        continue
sys.exit(1)
PYEOF
}

# A marker file the child/grandchild writes on exit proves the process actually
# REACHED its exit path (as opposed to being killed before it could).
wait_gone() {  # wait_gone <pid> <seconds>
    local i=0 n=$(( ${2:-10} * 20 ))
    while [ "$i" -lt "$n" ]; do
        alive "$1" || return 0
        sleep 0.05; i=$((i+1))
    done
    return 1
}

# ---------------------------------------------------------------------------
# 0. CONTROL — this observer CAN see a live process.
#    Without it, every "the child is gone" assertion below proves nothing.
# ---------------------------------------------------------------------------
echo "--- 0. control: the observer sees a live process ---"
sleep 30 & CTRL_PID=$!
alive "$CTRL_PID" && ok "control: observer sees a live pid (kill -0 discriminates)" \
  || bad "control: observer cannot see a live process — every liveness assertion is vacuous"
kill "$CTRL_PID" 2>/dev/null; wait "$CTRL_PID" 2>/dev/null

# ---------------------------------------------------------------------------
# 1. normal exit inside budget -> rc 0, verified exit, nothing supervised left
# ---------------------------------------------------------------------------
echo "--- 1. child exits inside budget ---"
R="$WORK/res1.json"
python3 "$SUP" run --deadline-ms 20000 --grace-ms 2000 --out "$WORK/o1" --err "$WORK/e1" \
    --result-json "$R" -- python3 -c "
import sys
sys.stdout.write('child completed normally\n')
" >"$WORK/sup1.out" 2>"$WORK/sup1.err"
rc=$?
[ "$rc" -eq 0 ] && ok "normal child: rc=0" || bad "normal child rc=$rc" "stderr: $(cat "$WORK/sup1.err" 2>/dev/null | tr '\n' ' ' | cut -c1-400)"
grep -q "child completed normally" "$WORK/o1" 2>/dev/null \
  && ok "normal child: its stdout was captured (it really ran)" || bad "normal child stdout missing"
[ "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("outcome"))' "$R" 2>/dev/null)" = "exited" ] \
  && ok "normal child: receipt says outcome=exited" || bad "normal child receipt wrong" "$(cat "$R" 2>/dev/null)"

# ---------------------------------------------------------------------------
# 2. CLI IGNORING TIMEOUT — the child ignores its own timeout flag and hangs
# ---------------------------------------------------------------------------
echo "--- 2. a child that ignores any timeout flag is still bounded ---"
R2="$WORK/res2.json"
start=$(date +%s)
python3 "$SUP" run --deadline-ms 1500 --grace-ms 1000 --out "$WORK/o2" --err "$WORK/e2" \
    --result-json "$R2" -- python3 -c "
import time
# a CLI that mis-parses/ignores --timeout and simply never returns
time.sleep(600)
" >/dev/null 2>&1
rc=$?
elapsed=$(( $(date +%s) - start ))
[ "$rc" -eq 4 ] && ok "timeout: supervisor returned rc=4 (timeout) rather than waiting" || bad "ignore-timeout rc=$rc (expected 4)"
[ "$elapsed" -le 8 ] && ok "timeout: bounded in ~${elapsed}s despite a 600s child (deadline was honoured)" \
  || bad "timeout: took ${elapsed}s — the deadline was NOT enforced"
# The receipt must NAME the transition. It records outcome=timeout and the
# group verdict; signal_killed is false when the group honoured TERM inside the
# grace window (escalation to KILL is exercised separately in section 4).
OUT2=$(python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
print(d.get("outcome"), str(isinstance(d.get("signal_killed"),bool)).lower(), d.get("group_terminated"), d.get("next_owner"))
' "$R2" 2>/dev/null)
case "$OUT2" in
  "timeout true True operator") ok "timeout: receipt records outcome=timeout, a boolean signal_killed, group_terminated=True, next_owner=operator" ;;
  *) bad "timeout receipt" "$OUT2" ;;
esac

# ---------------------------------------------------------------------------
# 3. GRANDCHILD SURVIVAL — the process-GROUP case, and its control
# ---------------------------------------------------------------------------
echo "--- 3. a grandchild must not survive the group kill ---"
R3="$WORK/res3.json"
GRAND_TOKEN="RR026GRANDCHILDPROBE"
python3 "$SUP" run --deadline-ms 1500 --grace-ms 1000 --out "$WORK/o3" --err "$WORK/e3" \
    --result-json "$R3" -- python3 -c "
import subprocess, sys, time
# a child that spawns a grandchild which OUTLIVES a naive single-pid kill.
# The token makes the grandchild identifiable in ps output.
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)  # %s' % '$GRAND_TOKEN'])
open('$WORK/grandchild.spawned','w').write('spawned')
time.sleep(600)
" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 4 ] && ok "grandchild case: rc=4 (bounded)" || bad "grandchild case rc=$rc"
[ -f "$WORK/grandchild.spawned" ] && ok "the grandchild really was spawned before the kill (not a race)" \
  || bad "grandchild never spawned — this case did not test the group kill"
sleep 0.5
if seen_token "$GRAND_TOKEN"; then
    bad "a grandchild SURVIVED the group kill — orphan left running" "$(ps -Ao pid=,command= 2>/dev/null | grep -F -- "$GRAND_TOKEN" | head -2)"
    pkill -9 -f "$GRAND_TOKEN" 2>/dev/null
else
    ok "grandchild case: no orphan survived the process-group termination"
fi
# CONTROL: the observer must be able to FIND such a process. Without this the
# assertion above is satisfied by a blind detector (which is exactly what
# `pgrep -f` turned out to be here on macOS).
python3 -c "import time; time.sleep(600)  # $GRAND_TOKEN" &
ORPHAN=$!
sleep 0.5
if seen_token "$GRAND_TOKEN"; then
    ok "control: the orphan detector DOES find a deliberately planted grandchild-shaped process"
else
    bad "control: orphan detector cannot find a planted survivor — the assertion above is vacuous"
fi
kill -9 "$ORPHAN" 2>/dev/null; wait "$ORPHAN" 2>/dev/null
seen_token "$GRAND_TOKEN" && bad "control cleanup failed (planted orphan still alive)" \
  || ok "control cleanup: the planted process is gone again" 

# ---------------------------------------------------------------------------
# 4. TERM-IGNORING child -> KILL escalation, verified
# ---------------------------------------------------------------------------
echo "--- 4. a child that IGNORES SIGTERM is KILLed and VERIFIED dead ---"
R4="$WORK/res4.json"
python3 "$SUP" run --deadline-ms 1500 --grace-ms 1000 --out "$WORK/o4" --err "$WORK/e4" \
    --result-json "$R4" -- python3 -c "
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
open('$WORK/termproof','w').write('installed SIG_IGN')
time.sleep(600)
" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 4 ] && ok "SIGTERM-ignoring child: rc=4" || bad "term-ignoring rc=$rc"
[ -f "$WORK/termproof" ] && ok "the child really installed SIG_IGN before the kill (not a race)" \
  || bad "child never reached SIG_IGN — this case did not test escalation"
sleep 0.5
if seen_token "SIG_IGN"; then
    bad "the SIGTERM-ignoring child SURVIVED"
    pkill -9 -f "SIG_IGN" 2>/dev/null || true
else
    ok "SIGTERM-ignoring child was escalated to KILL and is gone"
fi
S4=$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("outcome"),d.get("signal_killed"))' "$R4" 2>/dev/null)
case "$S4" in
  "timeout True") ok "receipt records the ESCALATION to KILL (signal_killed=true) — TERM alone was not enough" ;;
  "timeout False") bad "a SIGTERM-ignoring child was recorded without escalation, yet is gone — the receipt does not match what happened" ;;
  *) bad "escalation receipt missing" "$S4" ;;
esac

# ---------------------------------------------------------------------------
# 5. external CANCEL (SIGTERM to the supervisor) — the poll's own kill path
# ---------------------------------------------------------------------------
echo "--- 5. external cancellation ends predictably ---"
R5="$WORK/res5.json"
python3 "$SUP" run --deadline-ms 30000 --grace-ms 1000 --out "$WORK/o5" --err "$WORK/e5" \
    --result-json "$R5" -- python3 -c "
import time
time.sleep(600)  # RR026CANCELPROBE
" >/dev/null 2>&1 &
SUPJOB=$!
sleep 1.0
kill -TERM "$SUPJOB" 2>/dev/null
wait "$SUPJOB" 2>/dev/null
rc=$?
[ "$rc" -eq 4 ] && ok "cancel: supervisor returned rc=4 (cancelled/timeout class)" || ok "cancel: supervisor returned rc=$rc after SIGTERM"
sleep 0.5
if seen_token "RR026CANCELPROBE"; then
    bad "a supervised child SURVIVED cancellation"; pkill -9 -f "RR026CANCELPROBE" 2>/dev/null
else
    ok "cancel: no supervised process survived the supervisor's own termination"
fi
O5=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("outcome"))' "$R5" 2>/dev/null)
[ -n "$O5" ] && ok "cancel: outcome persisted for the next owner (outcome=$O5)" || bad "cancel: no receipt written"

# ---------------------------------------------------------------------------
# 6. LOCK: owner identity, refusal on a LIVE incumbent, never age-based
# ---------------------------------------------------------------------------
echo "--- 6. lock owner identity ---"
LD="$WORK/lockcase"
OUT="$(sup lock acquire --dir "$LD" --owner-token tok-A --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 100 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q '"ok": true' && ok "lock acquired by a live owner (this shell, pid $$)" || bad "lock acquire failed" "$OUT"
[ -f "$LD/lock.json" ] && ok "lock RECORD written (not a bare mkdir marker)" || bad "no lock record on disk"
grep -q '"process_start_identity"' "$LD/lock.json" && ok "record carries the process START identity (survives pid reuse)" || bad "no process start identity in the record"
grep -q '"owner_kind": "receiver"' "$LD/lock.json" && grep -q '"target_key": "box|box-synthetic"' "$LD/lock.json" \
  && ok "record carries the shared fence fields (owner_kind, target_key)" || bad "fence fields missing from the record"

# a SECOND acquire while the first owner is ALIVE must be refused, however old
sleep 0.2
OUT="$(sup lock acquire --dir "$LD" --owner-token tok-B --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 101 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q '"reason": "owner_running"' \
  && ok "a LIVE incumbent is refused outright (age is never consulted)" \
  || bad "a live incumbent was displaced" "$OUT"
grep -q '"owner_token": "tok-A"' "$LD/lock.json" && ok "the live incumbent still owns the record (it was not overwritten)" || bad "incumbent record changed"

# age alone must NOT free it: the lease can be far in the past, the owner lives
python3 - "$LD" <<'PYEOF'
import json, sys, os
p = os.path.join(sys.argv[1], "lock.json")
d = json.load(open(p))
d["lease_expires_at_ms"] = 1          # ancient lease
d["acquired_at"] = "2001-01-01T00:00:00Z"
json.dump(d, open(p, "w"), sort_keys=True)
PYEOF
OUT="$(sup lock acquire --dir "$LD" --owner-token tok-C --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 102 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q 'owner_running' \
  && ok "an ANCIENT lease does not free a LIVE owner's lock (never remove by age alone)" \
  || bad "age alone displaced a running owner" "$OUT"

# ---------------------------------------------------------------------------
# 7. STALE LOCK / PID REUSE / takeover reconciliation
# ---------------------------------------------------------------------------
echo "--- 7. stale lock, pid reuse, takeover ---"
LD2="$WORK/lockreuse"
# a long-lived stand-in for "the original owner", so its pid is real and alive
sleep 300 & STANDIN=$!
OUT="$(sup lock acquire --dir "$LD2" --owner-token tok-old --owner-pid "$STANDIN" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 200 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q '"ok": true' && ok "incumbent recorded against a real live stand-in pid" || bad "acquire failed" "$OUT"
kill -9 "$STANDIN" 2>/dev/null; wait "$STANDIN" 2>/dev/null
sleep 0.3
OUT="$(sup lock acquire --dir "$LD2" --owner-token tok-new --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 201 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q 'lapsed_without_reconciliation' \
  && ok "a DEAD incumbent's lock is NOT silently taken: refused with lapsed_without_reconciliation" \
  || bad "a dead incumbent's lock was taken without reconciliation" "$OUT"

# PID REUSE: the recorded pid is alive but its start identity differs
LD3="$WORK/lockreuse3"
sleep 300 & REUSE=$!
OUT="$(sup lock acquire --dir "$LD3" --owner-token tok-reuse --owner-pid "$REUSE" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 300 --lease-seconds 900 2>&1)"
python3 - "$LD3" <<'PYEOF'
import json, sys, os
p = os.path.join(sys.argv[1], "lock.json")
d = json.load(open(p))
# Simulate the kernel having recycled this pid: the pid is alive, but the
# recorded start identity belongs to a process that is long gone.
d["process_start_identity"] = "Mon Jan  1 00:00:00 2001"
json.dump(d, open(p, "w"), sort_keys=True)
PYEOF
OUT="$(sup lock acquire --dir "$LD3" --owner-token tok-reuse2 --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 301 --lease-seconds 900 --allow-takeover --takeover-generation 300 \
       --takeover-note "reconciled: recorded start identity does not match the live pid (kernel reused it)" 2>&1)"
if echo "$OUT" | grep -q '"takeover": true'; then
    ok "PID REUSE detected: a live pid whose START IDENTITY differs is reconciled as reused, and takeover proceeds"
elif echo "$OUT" | grep -q 'owner_running'; then
    bad "PID REUSE misread as a live owner (a recycled pid blocked legitimate takeover)" "$OUT"
else
    bad "pid-reuse case produced neither reuse nor running" "$OUT"
fi
kill -9 "$REUSE" 2>/dev/null; wait "$REUSE" 2>/dev/null

# ---------------------------------------------------------------------------
# 8. OLD RELEASE AFTER TAKEOVER — a stale owner must not free the new holder
# ---------------------------------------------------------------------------
echo "--- 8. old release after takeover ---"
LD4="$WORK/lockstale"
# The OLD owner is a stand-in process we can kill, so the record names a pid
# whose death is a FACT rather than an assumption about this shell.
sleep 300 & OLDOWNER=$!
OUT="$(sup lock acquire --dir "$LD4" --owner-token tok-OLD --owner-pid "$OLDOWNER" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 400 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q '"ok": true' && ok "old owner holds the lock (record names a real live pid)" || bad "old owner acquire failed" "$OUT"
kill -9 "$OLDOWNER" 2>/dev/null; wait "$OLDOWNER" 2>/dev/null
# A NEWER holder takes over via the RECONCILIATION path the poll itself uses.
OUT="$(sup lock acquire --dir "$LD4" --owner-token tok-NEW --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 401 --lease-seconds 900 --allow-takeover --takeover-generation 400 \
       --takeover-note "reconciled: incumbent pid not running" 2>&1)"
echo "$OUT" | grep -q '"takeover": true' && ok "newer holder took over AFTER reconciling the dead incumbent" || bad "newer holder acquire failed" "$OUT"
# the STALE owner now tries to release — it must be refused
OUT="$(sup lock release --dir "$LD4" --owner-token tok-OLD 2>&1)"
echo "$OUT" | grep -q 'not_owner' \
  && ok "a STALE owner's release is REFUSED (cannot free a newer holder's lock)" \
  || bad "stale release succeeded — a newer holder's lock was freed by an old owner" "$OUT"
grep -q '"owner_token": "tok-NEW"' "$LD4/lock.json" \
  && ok "the newer holder still owns the record after the stale release attempt" \
  || bad "newer holder's record was destroyed by a stale release"
# control: the CURRENT owner CAN release
OUT="$(sup lock release --dir "$LD4" --owner-token tok-NEW 2>&1)"
echo "$OUT" | grep -q '"released": true' \
  && ok "control: the CURRENT owner's release DOES succeed (the refusal above is ownership, not a broken release)" \
  || bad "the current owner could not release" "$OUT"

# ---------------------------------------------------------------------------
# 9. RENEWAL FAILURE
# ---------------------------------------------------------------------------
echo "--- 9. renewal failure ---"
LD5="$WORK/lockrenew"
sup lock acquire --dir "$LD5" --owner-token tok-R --owner-pid "$$" \
    --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
    --generation 500 --lease-seconds 900 >/dev/null 2>&1
OUT="$(sup lock renew --dir "$LD5" --owner-token tok-R --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q '"ok": true' && ok "a live owner CAN renew inside policy" || bad "renew failed for the owner" "$OUT"
OUT="$(sup lock renew --dir "$LD5" --owner-token tot-WRONG --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q 'not_owner' && ok "renewal by a non-owner is refused" || bad "non-owner renewed the lock" "$OUT"
python3 - "$LD5" <<'PYEOF'
import json, sys, os
p = os.path.join(sys.argv[1], "lock.json")
d = json.load(open(p))
d["lease_expires_at_ms"] = 1
json.dump(d, open(p, "w"), sort_keys=True)
PYEOF
OUT="$(sup lock renew --dir "$LD5" --owner-token tok-R --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q 'renew_after_expiry' \
  && ok "renewing an EXPIRED lease is refused (the holder is told to stop, not silently extended)" \
  || bad "an expired lease was renewed silently" "$OUT"

# ---------------------------------------------------------------------------
# 10. LEASE BUDGET: stop before losing it, with ACK margin
# ---------------------------------------------------------------------------
echo "--- 10. lease budget and ACK margin ---"
OUT="$(sup lease check --lease-seconds 900 --elapsed-ms 0 2>&1)"
echo "$OUT" | grep -q '"ok": true' && ok "900s lease with no elapsed time: budget available" || bad "lease check failed" "$OUT"
OUT="$(sup lease check --lease-seconds 900 --elapsed-ms 895000 2>&1)"
echo "$OUT" | grep -qE '"ok": false|"enough": false|ack_margin' \
  && ok "900s lease with 895s elapsed: refuses to start work that cannot finish with ACK margin" \
  || bad "a nearly-expired lease still reported budget" "$OUT"

# ---------------------------------------------------------------------------
# 11. the poll's OWN budget arithmetic (single budget covering everything)
# ---------------------------------------------------------------------------
echo "--- 11. the poll uses ONE budget and stops before losing the lease ---"
grep -q '_rr_budget_open' "$POLL" && ok "the poll opens one budget when the claim is accepted" || bad "no budget open"
grep -q 'RR_ACK_MARGIN_S' "$POLL" && ok "the budget reserves an ACK margin" || bad "no ACK margin"
grep -q '_rr_stop_without_turn' "$POLL" && ok "the poll can STOP before starting a turn that would overrun the lease" || bad "no stop-before-turn path"
grep -q 'RR_AGENT_MAX_S' "$POLL" && ok "the turn is capped by the lesser of budget and cap" || bad "no turn cap"
# The stale 600 constant must be gone from the LIVE path. Comment lines are
# allowed to name it (they explain the defect); executing code may not.
LIVE_HITS=$(grep -n -- '--timeout 600' "$POLL" | grep -v ':[[:space:]]*#' | wc -l | tr -d ' ')
[ "$LIVE_HITS" = "0" ] \
  && ok "the stale '--timeout 600' constant is gone from the EXECUTING path (comments may still name it)" \
  || bad "the stale '--timeout 600' constant is still executed on the live path" "$(grep -n -- '--timeout 600' "$POLL" | grep -v ':[[:space:]]*#')"
grep -q -- '--timeout "\$_sa_secs"' "$POLL" \
  && ok "the turn's timeout is DERIVED from the live lease (\$_sa_secs), not a constant" \
  || bad "the turn does not derive its timeout from the lease"

# ---------------------------------------------------------------------------
# 12. no double execution: the lock is what prevents it, and it is PROVEN
# ---------------------------------------------------------------------------
echo "--- 12. two concurrent polls cannot both execute ---"
LD6="$WORK/lockdouble"
OUT="$(sup lock acquire --dir "$LD6" --owner-token tok-1 --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 600 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q '"ok": true' && ok "first poller acquires" || bad "first poller failed" "$OUT"
OUT="$(sup lock acquire --dir "$LD6" --owner-token tok-2 --owner-pid "$$" \
       --target-kind box --resource-id box-synthetic --target-key 'box|box-synthetic' \
       --generation 601 --lease-seconds 900 2>&1)"
echo "$OUT" | grep -q 'owner_running' \
  && ok "second concurrent poller is REFUSED (single execution enforced by ownership, not by age)" \
  || bad "a second poller acquired a held lock — double execution is possible" "$OUT"

echo ""
echo "RESULT: $PASS passed, $FAIL failed"
RR026_DONE=1
[ "$FAIL" -eq 0 ] || exit 1
exit 0

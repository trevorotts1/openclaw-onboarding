#!/usr/bin/env bash
# tests/unit/orphan-process-prevention.test.sh — orphan-process prevention (fleet-wide)
#
# Proves a book-pipeline child cannot outlive its coordinator making :cloud
# calls forever. Uses 22-.../pipeline/orphan_guard.py exactly as orchestrator.py
# does (a MOCK long-runner links the SAME guard logic).
#
#   T1 (HEADLINE) PARENT-DEATH: start a mock run (child + grandchild) whose
#       logical parent is a mock coordinator; kill the coordinator; assert BOTH
#       the child AND its grandchild are GONE and the ":cloud call" counter has
#       STOPPED — no orphan survives.
#   T2 LOCK-REMOVAL: removing the liveness lockfile self-terminates the run.
#   T3 TARGETED REAP: reap-orchestrators.sh --run RID_A kills exactly run A's
#       group and leaves an unrelated run B untouched (never a blind pkill).
#   T4 SWEEP ORPHANS: --sweep reaps a run whose parent is dead, and does NOT
#       touch a run whose parent is alive.
#   T5 SINGLE-RUN SLUG LOCK: a second acquire for the same slug is refused.
#
# Offline, no network, no real orchestrator model calls. Requires setsid; skips
# with a clear note if unavailable (some minimal CI images).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIPE="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline"
GUARD="$PIPE/orphan_guard.py"
REAPER="$PIPE/reap-orchestrators.sh"
TMP="$(mktemp -d)"
RUN_DIR="$TMP/runs"; mkdir -p "$RUN_DIR"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
cleanup_all() {
    # belt-and-braces: never leave a test child alive
    for f in "$RUN_DIR"/*.pid; do
        [ -f "$f" ] || continue
        pg="$(sed -n 's/^pgid=//p' "$f")"; [ -n "${pg:-}" ] && kill -KILL -"$pg" 2>/dev/null || true
    done
    [ -n "${COORD:-}" ] && kill -KILL "$COORD" 2>/dev/null || true
    rm -rf "$TMP"
}
trap cleanup_all EXIT

echo "=== orphan-process-prevention.test.sh ==="
[ -f "$GUARD" ] || { echo "FAIL: orphan_guard.py not found"; exit 1; }

if ! python3 -c "import os,sys; sys.exit(0 if hasattr(os,'setsid') else 1)"; then
    echo "  SKIP: os.setsid unavailable on this platform"; exit 0
fi

alive() { kill -0 "$1" 2>/dev/null; }
# poll up to $2 tenths of a second for pid $1 to DISAPPEAR
wait_gone() {
    local pid="$1" tries="${2:-80}"
    while [ "$tries" -gt 0 ]; do
        alive "$pid" || return 0
        sleep 0.1; tries=$((tries-1))
    done
    return 1
}

# A mock orchestrator: links the REAL orphan_guard, spawns a grandchild
# (simulating the Phase-5 indexer subprocess), then loops "calling :cloud"
# (appending to a counter file). argv: <run_dir> <callfile> <gpidfile>
MOCK="$TMP/mock_orch.py"
cat > "$MOCK" <<PYEOF
import os, sys, time, subprocess
sys.path.insert(0, "$PIPE")
import orphan_guard as og
run_dir, callfile, gpidfile = sys.argv[1], sys.argv[2], sys.argv[3]
og.arm(run_dir=run_dir)                        # become group leader FIRST (setsid), then watchdog
gc = subprocess.Popen(["sleep", "600"])        # grandchild INHERITS the new group -> dies with us
open(gpidfile, "w").write(str(gc.pid))
while True:
    open(callfile, "a").write("call\n")        # simulate a :cloud request
    time.sleep(0.2)
PYEOF

# ── T1: PARENT-DEATH self-terminate (headline) ───────────────────────────────
bash -c 'sleep 300' & COORD=$!          # mock coordinator (the parent)
CALL1="$TMP/t1.calls"; GPID1="$TMP/t1.gpid"
OPENCLAW_RUN_ID="t1-run" OPENCLAW_PARENT_PID="$COORD" \
  OPENCLAW_RUN_DIR="$RUN_DIR" OPENCLAW_ORCH_DETACH=1 \
  OPENCLAW_WATCHDOG_INTERVAL_SEC=1 OPENCLAW_MAX_RUNTIME_SEC=3600 \
  python3 "$MOCK" "$RUN_DIR" "$CALL1" "$GPID1" &
MOCK1=$!
sleep 1.5                                        # let it run + spawn grandchild
GC1="$(cat "$GPID1" 2>/dev/null || echo 0)"
if alive "$MOCK1" && [ "$GC1" -gt 0 ] && alive "$GC1"; then
    kill -KILL "$COORD" 2>/dev/null; COORD=""    # KILL the coordinator (orphan the child)
    if wait_gone "$MOCK1" 100; then
        # grandchild must be gone too (process-GROUP cleanup)
        if wait_gone "$GC1" 40; then
            # PROOF of "no further :cloud calls": once the run is dead the call
            # counter must be STABLE (an orphan would keep incrementing it).
            c1="$(wc -l < "$CALL1" 2>/dev/null || echo 0)"
            sleep 0.8
            c2="$(wc -l < "$CALL1" 2>/dev/null || echo 0)"
            if [ "$c1" = "$c2" ]; then
                pass "T1: orphaned run self-terminated — child+grandchild gone, :cloud calls STOPPED (stable at $c2)"
            else
                fail "T1: :cloud calls still growing after death ($c1 -> $c2) — orphan alive"
            fi
        else
            fail "T1: grandchild ($GC1) survived — process-group cleanup failed"
        fi
    else
        fail "T1: mock child ($MOCK1) survived its dead parent — ORPHAN"
    fi
else
    fail "T1: mock run did not start cleanly (mock=$MOCK1 gc=$GC1)"
fi

# ── T2: LOCK-REMOVAL self-terminate ──────────────────────────────────────────
bash -c 'sleep 300' & COORD=$!
LOCK2="$RUN_DIR/t2-run.live"; : > "$LOCK2"
CALL2="$TMP/t2.calls"; GPID2="$TMP/t2.gpid"
OPENCLAW_RUN_ID="t2-run" OPENCLAW_PARENT_PID="$COORD" \
  OPENCLAW_RUN_LOCKFILE="$LOCK2" OPENCLAW_RUN_DIR="$RUN_DIR" OPENCLAW_ORCH_DETACH=1 \
  OPENCLAW_WATCHDOG_INTERVAL_SEC=1 python3 "$MOCK" "$RUN_DIR" "$CALL2" "$GPID2" &
MOCK2=$!
sleep 1.5
if alive "$MOCK2"; then
    rm -f "$LOCK2"                                # abort signal = remove the lock
    if wait_gone "$MOCK2" 100; then
        pass "T2: removing the liveness lock self-terminated the run"
    else
        fail "T2: run survived lock removal"
    fi
else
    fail "T2: mock2 did not start"
fi
kill -KILL "$COORD" 2>/dev/null; COORD=""

# ── T3: TARGETED reap hits exactly one run, not an unrelated one ──────────────
# Two independent runs with LIVE parents (so only an explicit reap stops them).
start_run() {  # $1=run_id $2=callfile $3=gpidfile ; echoes MOCK pid
    # NOTE: the child's stdout/stderr MUST be redirected off the command-
    # substitution pipe, else "$(start_run ...)" blocks until the background
    # child exits (classic bash gotcha).
    OPENCLAW_RUN_ID="$1" OPENCLAW_RUN_DIR="$RUN_DIR" OPENCLAW_ORCH_DETACH=1 \
      OPENCLAW_WATCHDOG_INTERVAL_SEC="${WD_INTERVAL:-1}" OPENCLAW_MAX_RUNTIME_SEC=3600 \
      python3 "$MOCK" "$RUN_DIR" "$2" "$3" >/dev/null 2>&1 & echo $!
}
MOCKA="$(start_run runA "$TMP/a.calls" "$TMP/a.gpid")"
MOCKB="$(start_run runB "$TMP/b.calls" "$TMP/b.gpid")"
sleep 1.2
if alive "$MOCKA" && alive "$MOCKB"; then
    OPENCLAW_RUN_DIR="$RUN_DIR" bash "$REAPER" --run runA >/dev/null 2>&1 || true
    if wait_gone "$MOCKA" 60 && alive "$MOCKB"; then
        pass "T3: --run reaped exactly run A; unrelated run B untouched (no blind pkill)"
    else
        fail "T3: targeted reap wrong (A gone? $(alive "$MOCKA" && echo no || echo yes); B alive? $(alive "$MOCKB" && echo yes || echo no))"
    fi
    OPENCLAW_RUN_DIR="$RUN_DIR" bash "$REAPER" --run runB >/dev/null 2>&1 || true
    wait_gone "$MOCKB" 60 || kill -KILL "$MOCKB" 2>/dev/null || true
else
    fail "T3: runs A/B did not both start"
    kill -KILL "$MOCKA" "$MOCKB" 2>/dev/null || true
fi

# ── T4: SWEEP reaps a parent-dead run, spares a parent-alive run ──────────────
# Use a LONG watchdog interval so the orphan's OWN watchdog will NOT fire during
# the test window — proving the SWEEP is what reaps it (defense-in-depth: in
# production the watchdog would also catch it).
bash -c 'sleep 300' & COORD_LIVE=$!
bash -c 'sleep 0.2' & COORD_DEAD=$!      # exits almost immediately => dead parent
MOCK_ORPHAN="$(WD_INTERVAL=3600 OPENCLAW_PARENT_PID="$COORD_DEAD" start_run runOrphan "$TMP/o.calls" "$TMP/o.gpid")"
MOCK_KEEP="$(WD_INTERVAL=3600 OPENCLAW_PARENT_PID="$COORD_LIVE" start_run runKeep "$TMP/k.calls" "$TMP/k.gpid")"
sleep 1.5                                        # COORD_DEAD has exited by now
OPENCLAW_RUN_DIR="$RUN_DIR" bash "$REAPER" --sweep >/dev/null 2>&1 || true
if wait_gone "$MOCK_ORPHAN" 80 && alive "$MOCK_KEEP"; then
    pass "T4: --sweep reaped the parent-dead run; parent-alive run survived"
else
    fail "T4: sweep wrong (orphan gone? $(alive "$MOCK_ORPHAN" && echo no || echo yes); keep alive? $(alive "$MOCK_KEEP" && echo yes || echo no))"
fi
OPENCLAW_RUN_DIR="$RUN_DIR" bash "$REAPER" --run runKeep >/dev/null 2>&1 || true
wait_gone "$MOCK_KEEP" 60 || kill -KILL "$MOCK_KEEP" 2>/dev/null || true
kill -KILL "$COORD_LIVE" 2>/dev/null || true

# ── T5: single-run-per-slug lock ─────────────────────────────────────────────
T5="$(python3 - "$PIPE" "$RUN_DIR" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import orphan_guard as og
run_dir = sys.argv[2]
a = og.acquire_slug_lock(run_dir, "voss-never-split-difference")
b = og.acquire_slug_lock(run_dir, "voss-never-split-difference")
print("OK" if (a is not None and b is None) else f"BAD a={a} b={b}")
PY
)"
if [ "$T5" = "OK" ]; then
    pass "T5: single-run slug lock refuses a second concurrent acquire"
else
    fail "T5: slug lock wrong: $T5"
fi

echo ""
echo "=== orphan-process-prevention: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0

#!/usr/bin/env bash
# browser-probe-timeout.test.sh -- proves the AUD-19 / FLEET-FIX B.1 fix:
#   (1) a hung probe is bounded by a hard timeout (never waits forever)
#   (2) on timeout, the FULL descendant process tree is killed -- zero orphans
#   (3) killing the WRAPPING script mid-run (simulating an operator `kill`)
#       also reaps the full descendant tree via the same trap mechanism
#   (4) the timeout ceiling cannot be exceeded even if a caller asks for more
#
# Fully hermetic: builds a real multi-generation process tree with `sleep`
# (standing in for node -> Chromium -> renderer) so "zero orphan processes"
# is checked against REAL OS process state via pgrep/kill -0, not mocked.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/browser-probe-timeout.sh"
PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== browser-probe-timeout.test.sh ==="
[[ -f "$LIB" ]] || { echo "FAIL: lib not found: $LIB"; exit 1; }
# shellcheck source=browser-probe-timeout.sh
source "$LIB"

# ─── helper: spawn a 3-generation process tree (grandparent/parent/child) ────
# that never exits on its own, standing in for node -> Chromium -> renderer.
# Returns (via echo) the PID of the top-level "node" stand-in.
spawn_fake_browser_tree() {
  # Every background process below explicitly closes/redirects its inherited
  # stdout -- otherwise a background grandchild holding open the pipe that
  # backs THIS function's own `$(...)` capture would hang the caller for the
  # full 300s (a classic bash command-substitution gotcha, unrelated to the
  # fix under test).
  bash -c '
    bash -c "sleep 300" >/dev/null 2>&1 &   # "renderer" grandchild
    wait
  ' >/dev/null 2>&1 &
  echo $!
}

# ─── T1: ab_kill_tree kills a multi-generation tree, not just the top PID ───
echo ""
echo "--- T1: ab_kill_tree reaps the FULL descendant tree ---"
TOP_PID="$(spawn_fake_browser_tree)"
sleep 0.5   # let the tree fully spawn
DESCENDANTS_BEFORE="$(pgrep -P "$TOP_PID" 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$DESCENDANTS_BEFORE" -ge 1 ]]; then
  pass "T1a: fake browser tree spawned with >=1 direct child (has $DESCENDANTS_BEFORE)"
else
  fail "T1a: fake browser tree did not spawn a child (setup broken, not the fix)"
fi
ab_kill_tree "$TOP_PID" TERM
sleep 0.5
if kill -0 "$TOP_PID" 2>/dev/null; then
  fail "T1b: top PID $TOP_PID still alive after ab_kill_tree"
else
  pass "T1b: top PID $TOP_PID reaped by ab_kill_tree"
fi
# Walk /bin/ps for any leftover "sleep 300" launched by this test (catches a
# grandchild ab_kill_tree failed to reach).
LEFTOVER="$(pgrep -f "sleep 300" 2>/dev/null || true)"
if [[ -z "$LEFTOVER" ]]; then
  pass "T1c: ZERO orphan 'sleep 300' processes remain (full tree reaped)"
else
  fail "T1c: orphan process(es) survived ab_kill_tree: $LEFTOVER"
fi

# ─── T2: ab_wait_with_timeout bounds a HUNG process and reaps its tree ──────
echo ""
echo "--- T2: ab_wait_with_timeout hard-bounds a hung probe + reaps its tree ---"
TOP_PID="$(spawn_fake_browser_tree)"
sleep 0.5
START="$(date +%s)"
ab_wait_with_timeout "$TOP_PID" 2   # 2s timeout against a 300s hang
RC=$?
END="$(date +%s)"
ELAPSED=$((END - START))
if [[ "$AB_PROBE_TIMED_OUT" -eq 1 && "$RC" -eq 124 ]]; then
  pass "T2a: ab_wait_with_timeout reports timeout (AB_PROBE_TIMED_OUT=1, rc=124)"
else
  fail "T2a: expected timeout signal, got AB_PROBE_TIMED_OUT=$AB_PROBE_TIMED_OUT rc=$RC"
fi
if [[ "$ELAPSED" -le 6 ]]; then
  pass "T2b: returned promptly at ~timeout (${ELAPSED}s), never waited for the 300s hang"
else
  fail "T2b: took ${ELAPSED}s -- did not bound the hang at the 2s timeout"
fi
sleep 0.5
if kill -0 "$TOP_PID" 2>/dev/null; then
  fail "T2c: top PID $TOP_PID still alive after timeout"
else
  pass "T2c: top PID $TOP_PID killed on timeout"
fi
LEFTOVER="$(pgrep -f "sleep 300" 2>/dev/null || true)"
if [[ -z "$LEFTOVER" ]]; then
  pass "T2d: ZERO orphan Chromium-stand-in processes remain after timeout"
else
  fail "T2d: orphan process(es) survived timeout: $LEFTOVER"
fi

# ─── T3: the timeout ceiling cannot be exceeded (clamped, never honored raw) ─
echo ""
echo "--- T3: AB_PROBE_MAX_TIMEOUT_SECS ceiling cannot be exceeded ---"
TOP_PID="$(spawn_fake_browser_tree)"
sleep 0.3
# Ask for way more than the 120s ceiling; override the ceiling itself down to
# 2s for THIS test run so we don't have to wait 120+ real seconds to prove
# the clamp fires (proves the clamp math, not merely the default).
AB_PROBE_MAX_TIMEOUT_SECS=2
START="$(date +%s)"
ab_wait_with_timeout "$TOP_PID" 999999
RC=$?
END="$(date +%s)"
ELAPSED=$((END - START))
AB_PROBE_MAX_TIMEOUT_SECS=120   # restore
if [[ "$RC" -eq 124 && "$ELAPSED" -le 6 ]]; then
  pass "T3: a 999999s request is CLAMPED to the ceiling (~2s), never honored raw (rc=124, ${ELAPSED}s)"
else
  fail "T3: ceiling not enforced -- rc=$RC elapsed=${ELAPSED}s"
fi
ab_kill_tree "$TOP_PID" KILL 2>/dev/null || true

# ─── T4: killing the WRAPPING process (simulated `kill` mid-run) still ──────
# reaps the full descendant tree, via the same node-PID-trap pattern
# 06-verify-agent-browser.sh registers (EXIT/INT/TERM -> ab_kill_tree).
echo ""
echo "--- T4: killing the wrapper mid-run still reaps the full tree (trap) ---"
WRAPPER_SCRIPT="$(mktemp)"
PIDFILE="$(mktemp)"
# Mirrors EXACTLY the pattern 06-verify-agent-browser.sh uses in production:
# background the probe, register the node-PID trap, then block on
# ab_wait_with_timeout's 1s-poll loop -- NOT a raw long sleep. (A raw
# multi-hundred-second foreground `sleep` would defer bash's own trap
# delivery until that sleep returns -- a real, separate bash gotcha this
# harness must avoid so it exercises the ACTUAL production wait pattern.)
cat > "$WRAPPER_SCRIPT" <<WRAPEOF
#!/usr/bin/env bash
set -uo pipefail
source "$LIB"
bash -c '
  bash -c "sleep 300" >/dev/null 2>&1 &
  wait
' >/dev/null 2>&1 &
CHILD_PID=\$!
echo "\$CHILD_PID" > "$PIDFILE"
trap 'ab_kill_tree "\$CHILD_PID" TERM' EXIT INT TERM
# Simulate the calling script blocked on the probe -- same 1s-poll wait the
# real 06-verify-agent-browser.sh uses (a long ceiling; we kill it manually
# well before it would ever fire on its own).
ab_wait_with_timeout "\$CHILD_PID" 300
WRAPEOF
chmod +x "$WRAPPER_SCRIPT"
bash "$WRAPPER_SCRIPT" &
WRAPPER_PID=$!
sleep 1   # let it spawn the fake browser tree and write the pidfile
CHILD_PID="$(cat "$PIDFILE" 2>/dev/null || echo "")"
if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
  pass "T4a: wrapper spawned its fake-browser child tree (pid $CHILD_PID alive)"
else
  fail "T4a: wrapper did not spawn a live child (setup broken, not the fix)"
fi
kill -TERM "$WRAPPER_PID" 2>/dev/null   # simulate: operator kills the probe mid-run
sleep 1.5
if kill -0 "$WRAPPER_PID" 2>/dev/null; then
  fail "T4b: wrapper process $WRAPPER_PID still alive after kill -TERM"
else
  pass "T4b: wrapper process $WRAPPER_PID terminated"
fi
if [[ -n "$CHILD_PID" ]] && kill -0 "$CHILD_PID" 2>/dev/null; then
  fail "T4c: child tree PID $CHILD_PID SURVIVED the wrapper being killed (orphan!)"
else
  pass "T4c: child tree PID $CHILD_PID reaped when the wrapper was killed (trap fired)"
fi
LEFTOVER="$(pgrep -f "sleep 300" 2>/dev/null || true)"
if [[ -z "$LEFTOVER" ]]; then
  pass "T4d: ZERO orphan Chromium-stand-in processes remain after killing the probe mid-run"
else
  fail "T4d: orphan process(es) survived: $LEFTOVER"
  pkill -f "sleep 300" 2>/dev/null || true   # cleanup so re-runs aren't polluted
fi
rm -f "$WRAPPER_SCRIPT" "$PIDFILE"

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [[ "$FAIL" -eq 0 ]]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi

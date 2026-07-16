#!/usr/bin/env bash
# qc-agent-browser-reaper-assert.test.sh — P3-06 step (c)4 regression test.
#
# Proves the reaper/doctor check upgraded from warn_only to assert for the
# POST-smoke-test state:
#   1. FAIL-FIRST: the PRE-FIX qc-agent-browser.sh has no post-test session
#      check AT ALL -- prove it PASSES even when a session is deliberately
#      left open after the smoke test (the exact gap P3-06 closes).
#   2. THE FIX: with a stub `close` that deliberately leaves its Chromium
#      stand-in process alive (a leaked session), qc-agent-browser.sh now
#      FAILS -- not warns.
#   3. The negative: a stub whose `close` actually tears down its process
#      leaves the QC clean (PASS), proving this isn't just permanently red.
#   4. A session that predates this run (planted BEFORE the smoke test) is
#      reported WARN, never FAIL — "not this skill's fault" stays true.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"
PRE_FIX_FIXTURE="/tmp/qc-agent-browser.sh.prefix-fixture"

source "$SCRIPT_DIR/lib-stub-agent-browser.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== qc-agent-browser-reaper-assert.test.sh (P3-06) ==="

WORK="$(mktemp -d)"
PIDFILE="$WORK/stub.pid"
PRE_PIDFILE="$WORK/pre-existing.pid"
cleanup() {
  kill_stub_pidfile "$PIDFILE"
  kill_stub_pidfile "$PRE_PIDFILE"
  # GK-28/U90: qc-agent-browser.sh now runs TWO open/close cycles per
  # invocation (Step-4 smoke test + the backstop conformance battery), both
  # against the same stub's single pidfile -- a deliberately leaked process
  # from ONE cycle can be clobbered out of that pidfile by the OTHER cycle's
  # own `open`. A pattern sweep is the only reliable belt-and-suspenders
  # cleanup (see lib-stub-agent-browser.sh for the full rationale).
  kill_all_agent_browser_chrome_stubs
  rm -rf "$WORK"
}
trap cleanup EXIT

stage_install() {
  local home="$1" staged="$1/.openclaw/skills/03-agent-browser"
  mkdir -p "$1/.openclaw/skills"
  cp -R "$SKILL_DIR" "$staged"
  echo "$staged"
}

# ── (1) FAIL-FIRST: pre-fix script has no post-test check; PASSES even with
#        a session deliberately leaked by `close`. ──────────────────────────
if [[ -f "$PRE_FIX_FIXTURE" ]]; then
  LEAK_BIN="$WORK/leak-bin"
  build_stub_agent_browser "$LEAK_BIN" "$PIDFILE" 1   # leak_mode=1: close doesn't kill
  HOME1="$WORK/home-prefix"
  STAGED1="$(stage_install "$HOME1")"
  cp "$PRE_FIX_FIXTURE" "$STAGED1/qc-agent-browser.sh"
  chmod +x "$STAGED1/qc-agent-browser.sh"
  if HOME="$HOME1" PATH="$LEAK_BIN:$PATH" bash "$STAGED1/qc-agent-browser.sh" >/tmp/p306-prefix-reaper-out.$$ 2>&1; then
    pass "fail-first: the PRE-FIX qc-agent-browser.sh PASSES even with a session left open after the smoke test -- proving the assert gate is new"
  else
    fail "expected the PRE-FIX script to PASS despite a leaked session (it had no post-test check) -- got: $(cat /tmp/p306-prefix-reaper-out.$$)"
  fi
  rm -f /tmp/p306-prefix-reaper-out.$$
  kill_stub_pidfile "$PIDFILE"
  kill_all_agent_browser_chrome_stubs   # GK-28/U90: see lib-stub-agent-browser.sh
else
  echo "  SKIP: pre-fix fixture not found at $PRE_FIX_FIXTURE"
fi

# ── (2) THE FIX: leaked session (stub close does NOT kill) -- FAILS, not warns.
LEAK_BIN2="$WORK/leak-bin2"
build_stub_agent_browser "$LEAK_BIN2" "$PIDFILE" 1
HOME2="$WORK/home-leak"
STAGED2="$(stage_install "$HOME2")"
OUT2="$(HOME="$HOME2" PATH="$LEAK_BIN2:$PATH" bash "$STAGED2/qc-agent-browser.sh" 2>&1)"
RC2=$?
if [[ "$RC2" -ne 0 ]] && echo "$OUT2" | grep -q "✗ FAIL — this smoke test's own Chromium process is still alive"; then
  pass "a session left open after the smoke test FAILS QC (not warns) -- assert upgrade proven"
else
  fail "expected a hard FAIL line for the leaked session and non-zero exit; rc=$RC2, output: $OUT2"
fi
if echo "$OUT2" | grep -qE "⚠ WARN.*this smoke test's own Chromium"; then
  fail "the leaked-session line is still WARN-worded -- assert upgrade did not actually happen"
fi
kill_stub_pidfile "$PIDFILE"
# GK-28/U90: case (2) deliberately leaks (LEAK_MODE=1) — a hard sweep here is
# load-bearing, not cosmetic: qc-agent-browser.sh now runs a SECOND
# open/close cycle (the conformance battery) after Step-4 within the SAME
# run, which clobbers this stub's single pidfile with its own (cleanly
# closed) pid — so Step-4's genuinely leaked process is no longer reachable
# via $PIDFILE by the time this line runs. Without this sweep it survives
# into case (3)/(4) and inflates their pre-existing-process counts (see
# lib-stub-agent-browser.sh for the full rationale).
kill_all_agent_browser_chrome_stubs

# ── (3) Negative: a well-behaved close (stub actually kills) -- clean PASS ──
CLEAN_BIN="$WORK/clean-bin"
build_stub_agent_browser "$CLEAN_BIN" "$PIDFILE" 0
HOME3="$WORK/home-clean"
STAGED3="$(stage_install "$HOME3")"
OUT3="$(HOME="$HOME3" PATH="$CLEAN_BIN:$PATH" bash "$STAGED3/qc-agent-browser.sh" 2>&1)"
RC3=$?
if [[ "$RC3" -eq 0 ]] && echo "$OUT3" | grep -q "✓ PASS — zero Chromium processes spawned by this smoke test remain alive"; then
  pass "a session that closes cleanly PASSES QC (the gate isn't permanently red)"
else
  fail "expected a clean PASS for a well-behaved close; rc=$RC3, output: $OUT3"
fi
kill_stub_pidfile "$PIDFILE"
kill_all_agent_browser_chrome_stubs

# ── (4) A session pre-existing BEFORE this run -- WARN, never FAIL ──────────
PREEXIST_BIN="$WORK/preexist-bin"
build_stub_agent_browser "$PREEXIST_BIN" "$PIDFILE" 0   # this run's own close works cleanly
HOME4="$WORK/home-preexist"
STAGED4="$(stage_install "$HOME4")"
# Plant a pre-existing scoped Chromium stand-in BEFORE the QC run starts.
( exec -a "chrome --user-data-dir=/tmp/agent-browser-chrome-preexist-stub" sleep 300 ) &
echo "$!" > "$PRE_PIDFILE"
OUT4="$(HOME="$HOME4" PATH="$PREEXIST_BIN:$PATH" bash "$STAGED4/qc-agent-browser.sh" 2>&1)"
RC4=$?
if [[ "$RC4" -eq 0 ]] \
   && echo "$OUT4" | grep -q "⚠ WARN — 1 pre-existing scoped agent-browser Chromium process" \
   && ! echo "$OUT4" | grep -q "✗ FAIL — this smoke test's own Chromium process"; then
  pass "a pre-existing session (planted before this run) is reported WARN, never FAIL, and QC still PASSES overall"
else
  fail "expected a WARN-only pre-existing line and overall PASS; rc=$RC4, output: $OUT4"
fi
kill_stub_pidfile "$PIDFILE"
kill_stub_pidfile "$PRE_PIDFILE"

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

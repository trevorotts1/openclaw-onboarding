#!/usr/bin/env bash
# qc-agent-browser-headed-refuse.test.sh — P3-06 step (c)3 regression test.
#
# Proves: an ambient AGENT_BROWSER_HEADED signal that would force a visible
# window makes qc-agent-browser.sh REFUSE the Step-4 smoke test (exit-75
# class, matching Skill 06's D6 convention) instead of silently running
# headed. Also proves the negative: without the ambient signal, the smoke
# test proceeds normally.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"

source "$SCRIPT_DIR/lib-stub-agent-browser.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== qc-agent-browser-headed-refuse.test.sh (P3-06) ==="

WORK="$(mktemp -d)"
PIDFILE="$WORK/stub.pid"
cleanup() { kill_stub_pidfile "$PIDFILE"; rm -rf "$WORK"; }
trap cleanup EXIT

STUB_BIN="$WORK/bin"
build_stub_agent_browser "$STUB_BIN" "$PIDFILE" 0

HOME_DIR="$WORK/home"
STAGED="$HOME_DIR/.openclaw/skills/03-agent-browser"
mkdir -p "$HOME_DIR/.openclaw/skills"
cp -R "$SKILL_DIR" "$STAGED"

# ── (1) AGENT_BROWSER_HEADED=true ambient -- must REFUSE ─────────────────────
OUT1="$(HOME="$HOME_DIR" PATH="$STUB_BIN:$PATH" AGENT_BROWSER_HEADED=true bash "$STAGED/qc-agent-browser.sh" 2>&1)"
RC1=$?
if [[ "$RC1" -ne 0 ]] && echo "$OUT1" | grep -q "REFUSE: AGENT_BROWSER_HEADED='true'" && echo "$OUT1" | grep -q "exit 75 class"; then
  pass "AGENT_BROWSER_HEADED=true ambient is REFUSED (exit-75 class), QC exits non-zero"
else
  fail "expected a REFUSE + exit-75-class message and non-zero exit with AGENT_BROWSER_HEADED=true; rc=$RC1, output: $OUT1"
fi
kill_stub_pidfile "$PIDFILE"

# ── (2) A few other truthy spellings also refuse (1, TRUE) ──────────────────
OUT2="$(HOME="$HOME_DIR" PATH="$STUB_BIN:$PATH" AGENT_BROWSER_HEADED=1 bash "$STAGED/qc-agent-browser.sh" 2>&1)"
if echo "$OUT2" | grep -q "REFUSE: AGENT_BROWSER_HEADED='1'"; then
  pass "AGENT_BROWSER_HEADED=1 ambient is also REFUSED"
else
  fail "expected AGENT_BROWSER_HEADED=1 to be refused too; output: $OUT2"
fi
kill_stub_pidfile "$PIDFILE"

# ── (3) No ambient signal -- smoke test proceeds normally (not refused) ─────
OUT3="$(HOME="$HOME_DIR" PATH="$STUB_BIN:$PATH" bash "$STAGED/qc-agent-browser.sh" 2>&1)"
RC3=$?
if ! echo "$OUT3" | grep -q "REFUSE: AGENT_BROWSER_HEADED"; then
  pass "with no ambient AGENT_BROWSER_HEADED, the smoke test is NOT refused (runs normally)"
else
  fail "smoke test was unexpectedly refused with no ambient signal set; output: $OUT3"
fi
kill_stub_pidfile "$PIDFILE"

# ── (4) Explicit AGENT_BROWSER_HEADED=false ambient -- also proceeds ────────
OUT4="$(HOME="$HOME_DIR" PATH="$STUB_BIN:$PATH" AGENT_BROWSER_HEADED=false bash "$STAGED/qc-agent-browser.sh" 2>&1)"
if ! echo "$OUT4" | grep -q "REFUSE: AGENT_BROWSER_HEADED"; then
  pass "AGENT_BROWSER_HEADED=false ambient proceeds normally (headless, as required)"
else
  fail "AGENT_BROWSER_HEADED=false was incorrectly refused; output: $OUT4"
fi
kill_stub_pidfile "$PIDFILE"

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

#!/usr/bin/env bash
# qc-agent-browser-drift-gate.test.sh — P3-06 step (c)2 regression test.
#
# FAIL-FIRST: run against a checked-out copy of the ORIGINAL (pre-P3-06)
# qc-agent-browser.sh -- which has NO archive-drift check at all -- and prove
# it does NOT catch a corrupted archive (silently PASSes). Then run the SAME
# corruption against the FIXED script in this repo and prove it FAILS,
# naming the differing file. Finally, prove a byte-identical archive PASSES
# clean.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"
QC_SCRIPT="$SKILL_DIR/qc-agent-browser.sh"
PRE_FIX_FIXTURE="/tmp/qc-agent-browser.sh.prefix-fixture"

source "$SCRIPT_DIR/lib-stub-agent-browser.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== qc-agent-browser-drift-gate.test.sh (P3-06) ==="

WORK="$(mktemp -d)"
PIDFILE="$WORK/stub.pid"
cleanup() { kill_stub_pidfile "$PIDFILE"; rm -rf "$WORK"; }
trap cleanup EXIT

STUB_BIN="$WORK/bin"
build_stub_agent_browser "$STUB_BIN" "$PIDFILE" 0

stage_install() {
  # Stages a simulated install: $1 = HOME dir to create, corrupt=$2 (0|1)
  local home="$1" corrupt="$2" staged="$1/.openclaw/skills/03-agent-browser"
  mkdir -p "$1/.openclaw/skills"
  cp -R "$SKILL_DIR" "$staged"
  if [[ "$corrupt" == "1" ]]; then
    python3 -c "
p = '$staged/INSTALL.md'
d = bytearray(open(p, 'rb').read())
i = len(d) // 2
d[i] = (d[i] + 1) % 256
open(p, 'wb').write(bytes(d))
"
  fi
  echo "$staged"
}

# ── (1) FAIL-FIRST: the PRE-FIX qc-agent-browser.sh (captured from
#        origin/main before this unit ran) has NO drift check -- prove it
#        silently PASSES even with a corrupted INSTALL.md sitting right next
#        to an untouched (now-stale-relative-to-source) archive. ────────────
if [[ -f "$PRE_FIX_FIXTURE" ]]; then
  HOME_CORRUPT="$WORK/home-prefix-corrupt"
  STAGED="$(stage_install "$HOME_CORRUPT" 1)"
  cp "$PRE_FIX_FIXTURE" "$STAGED/qc-agent-browser.sh"
  chmod +x "$STAGED/qc-agent-browser.sh"
  if HOME="$HOME_CORRUPT" PATH="$STUB_BIN:$PATH" bash "$STAGED/qc-agent-browser.sh" >/tmp/p306-prefix-out.$$ 2>&1; then
    pass "fail-first: the PRE-FIX qc-agent-browser.sh (no drift check) PASSES even with a corrupted INSTALL.md next to a now-mismatched archive -- proving the gate is new, not pre-existing"
  else
    fail "expected the PRE-FIX script to PASS despite drift (it has no drift check) -- got a failure, so this isn't proving what it claims: $(cat /tmp/p306-prefix-out.$$)"
  fi
  rm -f /tmp/p306-prefix-out.$$
else
  echo "  SKIP: pre-fix fixture not found at $PRE_FIX_FIXTURE (build-time artifact; not required for the fixed-script proofs below)"
fi

# ── (2) THE FIX: same corruption, the FIXED script in this repo -- FAILS,
#        naming INSTALL.md. ───────────────────────────────────────────────
HOME_CORRUPT2="$WORK/home-fixed-corrupt"
STAGED2="$(stage_install "$HOME_CORRUPT2" 1)"
OUT2="$(HOME="$HOME_CORRUPT2" PATH="$STUB_BIN:$PATH" bash "$STAGED2/qc-agent-browser.sh" 2>&1)"
RC2=$?
if [[ "$RC2" -ne 0 ]] && echo "$OUT2" | grep -q "STALE vs on-disk source. Differing file(s): INSTALL.md"; then
  pass "the FIXED qc-agent-browser.sh FAILS on the corrupted archive, naming exactly INSTALL.md"
else
  fail "expected the fixed script to FAIL naming INSTALL.md; rc=$RC2, output: $OUT2"
fi

# ── (3) Clean (uncorrupted) staged install -- archive drift section PASSES ──
HOME_CLEAN="$WORK/home-clean"
STAGED3="$(stage_install "$HOME_CLEAN" 0)"
OUT3="$(HOME="$HOME_CLEAN" PATH="$STUB_BIN:$PATH" bash "$STAGED3/qc-agent-browser.sh" 2>&1)"
if echo "$OUT3" | grep -q "PASS — agent-browser.skill matches on-disk"; then
  pass "a byte-identical archive PASSES the drift gate on a clean staged install"
else
  fail "expected the drift-gate PASS line on a clean install; output: $OUT3"
fi

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

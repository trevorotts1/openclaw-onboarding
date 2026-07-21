#!/usr/bin/env bash
# backstop-conformance.test.sh — GK-28/U90 step (c) regression test.
#
# Proves lib-backstop-conformance.sh's run_conformance_battery:
#   1. PASSES clean (rc=0, all five legs OK) against a well-behaved stub CLI.
#   2. FAILS -- naming the specific broken leg -- when ANY ONE of the
#      capabilities the real consumers (Skill 6's browser_manager.sh,
#      Skill 44's Tier-4 fallback) actually script is stubbed OUT: open,
#      ref-based snapshot, snapshot-ref STABILITY across calls, fill-by-ref,
#      a fill that SILENTLY NO-OPS, and guaranteed close (leaked-process
#      read-back). Each capability is broken ONE AT A TIME (fail-first,
#      per-leg) -- a battery that only ever passes or only ever fails is
#      worthless; this proves it discriminates.
#
#      The fill_noop case (T0-26) is the one this suite previously blessed: the
#      bundled clean stub echoed a filled message and exited 0 without mutating
#      anything, leg 4 checked only exit status, and line 59 below expected that
#      stub to PASS every leg. The stub now performs a real mutation, leg 4 reads
#      the value back, and a no-op fill is a distinct break mode that MUST fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && cd .. && pwd)"

# shellcheck source=../lib-backstop-conformance.sh
source "$SCRIPT_DIR/../lib-backstop-conformance.sh"
# shellcheck source=./lib-stub-agent-browser.sh
source "$SCRIPT_DIR/lib-stub-agent-browser.sh"   # kill_stub_pidfile only

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL + 1)); }

echo "=== backstop-conformance.test.sh (GK-28/U90) ==="

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

run_case() {
  # $1=label $2=break-capability("" = clean) $3=expect("pass"|"fail") $4=needle (fail only)
  local label="$1" brk="$2" expect="$3" needle="${4:-}"
  local tag="$$-$RANDOM"
  local bindir="$WORK/bin-$tag" pidfile="$WORK/pid-$tag" statedir="$WORK/state-$tag"
  build_conformance_stub "$bindir" "$pidfile" "$statedir" "$brk"

  local out rc=0
  out="$(PATH="$bindir:$PATH" run_conformance_battery "battery-test-$tag" "https://example.invalid/conformance-fixture" 2>&1)" || rc=$?
  kill_stub_pidfile "$pidfile"

  if [ "$expect" = "pass" ]; then
    if [ "$rc" -eq 0 ]; then
      pass "$label (clean run, all five legs PASS, rc=0)"
    else
      fail "$label expected rc=0, got rc=$rc: $out"
    fi
  else
    if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "$needle"; then
      pass "$label (correctly FAILS, naming: \"$needle\")"
    else
      fail "$label expected non-zero rc naming '$needle'; rc=$rc, output: $out"
    fi
  fi
}

run_case "clean stub — all five legs"                    ""                    pass
run_case "open capability broken (leg 1)"                 "open"                fail "open FAILED"
run_case "snapshot capability broken (leg 2)"             "snapshot"            fail "did NOT return any ref-based element"
run_case "snapshot-ref stability broken (leg 3)"          "snapshot_stability"  fail "NOT stable across repeated snapshots"
run_case "fill-by-ref capability broken (leg 4)"          "fill"                fail "fill by ref FAILED"
# THE SILENT ONE. The stub accepts the fill argv, prints FILLED and exits 0 while
# mutating nothing. Exit status alone cannot tell it from a working CLI -- before
# leg 4 read the field back, this stub PASSED the whole battery. It must FAIL.
run_case "fill is a silent NO-OP (leg 4 read-back)"       "fill_noop"           fail "did NOT hold the written value"
run_case "guaranteed-close leak (leg 5)"                  "close"               fail "leaked pid"

echo ""
echo "================================================="
echo "Results: $PASS passed, $FAIL failed"
echo "================================================="
if [ "$FAIL" -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "TESTS FAILED"
  exit 1
fi

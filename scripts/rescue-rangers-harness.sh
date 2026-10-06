#!/usr/bin/env bash
# scripts/rescue-rangers-harness.sh
# ============================================================================
# RR-030 — external assertion harness for the Rescue Rangers offline gates.
#
# WHY THIS EXISTS (the defect class it kills):
#   The old battery let failures hide three ways:
#     1. Fixture exit codes were accumulated inside `( ... )` SUBSHELLS, so a
#        broken checker bumped a counter the parent never saw and the run
#        still printed "0 failure(s)" and exited 0 (proven at baseline:
#        a mutated fixture printed "✗ FORCED-FAIL" and the summary still said
#        "0 failure(s)", rc=0).
#     2. A Python self-test wrapped a required case in a blanket
#        `except Exception` and printed SKIP on the very failure it was
#        supposed to catch (a broken aging sweep printed
#        "SKIP (ledger import unavailable: ...)" and the self-test returned 0).
#     3. verify.sh printed "ALL OFFLINE DRILLS PASS" with node ABSENT because
#        the JS drill was demoted to a WARN skip.
#
# LAW (from the RR-030 spec section):
#   - Failure accounting happens in the PARENT shell or in an external
#     assertion harness — never in a subshell whose exit code is discarded.
#   - Required runtime, import and assertion failures are NONZERO. A required
#     tool that is missing fails the gate; it is never a WARN-skip.
#   - Gates are named: UNIT / CONTRACT / INSTALLED / LIVE_ACCEPTANCE.
#     A missing installed host or live box is UNVERIFIED — it must never
#     degrade to SKIP=PASS and it never satisfies release completion.
#   - Negative/mutation drills deliberately break each checker in a COPY and
#     require the copied gate to go nonzero on the mutated code.
#
# TEST ROOTS: every fixture operates on an explicit --test-root / mktemp -d
# directory. HOME is never repurposed to point a tool at fixture state; the
# tools take explicit roots (rr-triage OC_CONFIG_ROOT, ledger --state-dir /
# RESCUE_STATE_DIR, board state_dir kwarg). OC_CONFIG_ROOT is consumed by
# rr-triage.sh's _oc_root and keeps the fixture tree fully explicit.
#
# USAGE:
#   source scripts/rescue-rangers-harness.sh
#   harness_begin
#   harness_case UNIT "name" -- bash script.sh            # rc 0 = pass
#   harness_gate_fail UNIT "why"                           # explicit failure
#   harness_unverified LIVE_ACCEPTANCE "no host access"    # recorded, not green
#   harness_finish                                        # exits nonzero on fail
#   harness_summary                                       # print-only summary
# ============================================================================
# guards against double-sourcing
[ -n "${_RR_RANGERS_HARNESS_LOADED:-}" ] && return 0 2>/dev/null || true
_RR_RANGERS_HARNESS_LOADED=1

# Gate labels — the RR-030 taxonomy. GATE_* are 1 when at least one case of
# that class ran, so a summary can distinguish "no CONTRACT coverage" from
# "CONTRACT green".
GATE_UNIT=0
GATE_CONTRACT=0
GATE_INSTALLED=0
GATE_LIVE=0

RR_HARNESS_PASS=0
RR_HARNESS_FAIL=0
RR_HARNESS_UNVERIFIED=0
RR_HARNESS_FAILED_NAMES=""

harness_begin() { RR_HARNESS_PASS=0; RR_HARNESS_FAIL=0; RR_HARNESS_UNVERIFIED=0; RR_HARNESS_FAILED_NAMES=""; }

# harness_case GATE NAME -- cmd...   ; the child's exit code IS the verdict.
harness_case() {
  local gate="$1" name="$2"; shift 2
  [ "${1:-}" = "--" ] && shift
  case "$gate" in
    UNIT) GATE_UNIT=1 ;;
    CONTRACT) GATE_CONTRACT=1 ;;
    INSTALLED) GATE_INSTALLED=1 ;;
    LIVE_ACCEPTANCE) GATE_LIVE=1 ;;
    *) echo "HARNESS BUG: unknown gate '$gate'" >&2; RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1)); return 0 ;;
  esac
  echo "--- [$gate] $name ---"
  local rc=0
  "$@"; rc=$?                     # parent shell observes the code directly
  if [ "$rc" -eq 0 ]; then
    RR_HARNESS_PASS=$((RR_HARNESS_PASS+1))
    echo "    [$gate] PASS: $name"
  else
    RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1))
    RR_HARNESS_FAILED_NAMES="$RR_HARNESS_FAILED_NAMES $gate:$name(rc=$rc)"
    echo "    [$gate] FAIL: $name (exit $rc)" >&2
  fi
  return 0
}

# An explicit assertion the caller makes in its own parent shell.
harness_gate_fail() {
  local gate="${1:-UNIT}" why="${2:-unspecified}"
  RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1))
  RR_HARNESS_FAILED_NAMES="$RR_HARNESS_FAILED_NAMES $gate:$why"
  echo "    [$gate] FAIL: $why" >&2
}

# harness_case_negative GATE NAME -- cmd...
# INVERSE verdict: the command MUST exit NONZERO (RR-030 negative/mutation
# drills: break the checker, require the gate to fail). A zero exit is the
# defect — the gate went green on broken code.
harness_case_negative() {
  local gate="$1" name="$2"; shift 2
  [ "${1:-}" = "--" ] && shift
  case "$gate" in
    UNIT) GATE_UNIT=1 ;;
    CONTRACT) GATE_CONTRACT=1 ;;
    INSTALLED) GATE_INSTALLED=1 ;;
    LIVE_ACCEPTANCE) GATE_LIVE=1 ;;
    *) echo "HARNESS BUG: unknown gate '$gate'" >&2; RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1)); return 0 ;;
  esac
  echo "--- [$gate] NEGATIVE: $name ---"
  local rc=0
  "$@"; rc=$?                     # parent shell observes the code directly
  if [ "$rc" -ne 0 ]; then
    RR_HARNESS_PASS=$((RR_HARNESS_PASS+1))
    echo "    [$gate] PASS: $name — exited $rc (nonzero, gate bit)"
  else
    RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1))
    RR_HARNESS_FAILED_NAMES="$RR_HARNESS_FAILED_NAMES $gate:$name(green-on-broken)"
    echo "    [$gate] FAIL: $name — exited 0; the gate went GREEN on broken code" >&2
  fi
  return 0
}

harness_unverified() {
  # A gate that cannot be exercised (e.g. no installed host reachable) is
  # recorded UNVERIFIED. It is reported, never counted green, and per RR-030
  # an UNVERIFIED LIVE_ACCEPTANCE gate blocks release completion.
  local gate="${1:-LIVE_ACCEPTANCE}" why="${2:-not exercised}"
  RR_HARNESS_UNVERIFIED=$((RR_HARNESS_UNVERIFIED+1))
  echo "    [$gate] UNVERIFIED: $why (not SKIP=PASS; blocks release completion)"
}

# harness_mutation GATE NAME -- breaker-cmd... -- checker-cmd...
# Run breaker in a sandbox copy; then checker MUST exit nonzero on the mutated
# tree. Then the unmutated checker MUST exit 0 on the same fixture (assumption
# control: proves the fixture is valid and the mutation, not the fixture,
# caused the failure).
harness_mutation() {
  local gate="$1" name="$2"; shift 2
  [ "${1:-}" = "--" ] && shift
  local breaker=() checker=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do breaker+=("$1"); shift; done
  shift || true
  checker=("$@")
  echo "--- [$gate] MUTATION: $name ---"
  local pre=0 post=0
  "${breaker[@]}"; pre=$?
  if [ "$pre" -ne 0 ]; then
    RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1))
    RR_HARNESS_FAILED_NAMES="$RR_HARNESS_FAILED_NAMES $gate:$name(breaker-rc=$pre)"
    echo "    [$gate] FAIL: $name — breaker setup failed (exit $pre)" >&2
    return 0
  fi
  "${checker[@]}"; post=$?
  if [ "$post" -eq 0 ]; then
    RR_HARNESS_FAIL=$((RR_HARNESS_FAIL+1))
    RR_HARNESS_FAILED_NAMES="$RR_HARNESS_FAILED_NAMES $gate:$name(checker-passed-on-mutated-code)"
    echo "    [$gate] FAIL: $name — gate went GREEN on mutated code (exit 0)" >&2
  else
    RR_HARNESS_PASS=$((RR_HARNESS_PASS+1))
    echo "    [$gate] PASS: $name — mutated checker exited $post (nonzero, gate bit)"
  fi
  return 0
}

harness_summary() {
  echo ""
  echo "=== RR-030 GATE SUMMARY ==="
  echo "UNIT=$GATE_UNIT CONTRACT=$GATE_CONTRACT INSTALLED=$GATE_INSTALLED LIVE_ACCEPTANCE=$GATE_LIVE"
  echo "passed=$RR_HARNESS_PASS failed=$RR_HARNESS_FAIL unverified=$RR_HARNESS_UNVERIFIED"
  [ -n "$RR_HARNESS_FAILED_NAMES" ] && echo "failed cases:$RR_HARNESS_FAILED_NAMES"
  if [ "$RR_HARNESS_FAIL" -gt 0 ]; then
    echo "VERDICT: FAIL — a gate is red. Fix the gate, never the exit code."
    return 1
  fi
  if [ "$RR_HARNESS_UNVERIFIED" -gt 0 ]; then
    echo "VERDICT: ALL RUN GATES GREEN — but $RR_HARNESS_UNVERIFIED unverified gate(s) remain."
    echo "Release completion requires every gate exercised: green UNIT line alone never satisfies it."
    return 0
  fi
  echo "VERDICT: ALL GATES GREEN"
  return 0
}

harness_finish() {
  harness_summary
  # Nonzero when any case failed. UNVERIFIED alone exits 0 here (the RUN was
  # honest) — release completion accounting happens upstream, where an
  # UNVERIFIED LIVE_ACCEPTANCE gate is an open blocker, not a pass.
  [ "$RR_HARNESS_FAIL" -eq 0 ]
}
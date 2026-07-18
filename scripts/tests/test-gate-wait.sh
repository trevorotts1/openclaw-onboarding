#!/usr/bin/env bash
# ============================================================
# scripts/tests/test-gate-wait.sh — gate-wait.sh regression tests
# ============================================================
# gate-wait.sh is the bounded foreground gate-poll tool that fixes the
# subagent background-hang failure mode (see the header comment in
# scripts/gate-wait.sh for the full root-cause writeup). These tests exist
# because that fix previously shipped with ZERO automated coverage — the
# single most important property (a hung inner command cannot push the
# script past its own deadline) was asserted only in prose.
#
# WHAT IS VERIFIED:
#   T1: --help exits 0 (not a usage error)
#   T2: an immediately-passing check exits 0 (GREEN)
#   T3: an immediately-failing check exits 1 (FAIL)
#   T4: a hanging inner command (`sleep 10`, --max-seconds 1) is bounded —
#       exits 2 (PENDING, not a false failure) within ~3s, not ~10s. This is
#       the whole point of the fix: the OUTER loop being bounded is not
#       enough if a single INNER call can hang past the deadline.
#   T5: the process spawned by the hanging command in T4 does not survive
#       as an orphan after gate-wait.sh returns (run_capped must actually
#       kill it, not just stop waiting on it).
#
# Usage: bash scripts/tests/test-gate-wait.sh
# Exit 0 = all pass. Exit 1 = one or more failures.
# ============================================================

set -u

PASS=0
FAIL=0
FAIL_MSGS=()

pass() { PASS=$((PASS+1)); printf '  ok %s\n' "$1"; }
fail() { FAIL=$((FAIL+1)); FAIL_MSGS+=("$1"); printf '  NOT ok %s\n' "$1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_WAIT="$SCRIPT_DIR/../gate-wait.sh"

if [ ! -f "$GATE_WAIT" ]; then
  echo "test-gate-wait.sh: cannot find gate-wait.sh at $GATE_WAIT" >&2
  exit 1
fi

# ── T1: --help exits 0 ──────────────────────────────────────────────────────
HELP_OUT="$(bash "$GATE_WAIT" --help 2>&1)"
HELP_RC=$?
if [ "$HELP_RC" -eq 0 ]; then
  pass "T1: --help exits 0 (got $HELP_RC)"
else
  fail "T1: --help exits 0 (got $HELP_RC)"
fi
case "$HELP_OUT" in
  *USAGE*) : ;;
  *) fail "T1b: --help output contains a USAGE section" ;;
esac

# ── T2: immediate pass exits 0 ──────────────────────────────────────────────
bash "$GATE_WAIT" cmd 'echo READY' --pass 'READY' --fail 'NEVER_MATCHES_XYZ' \
  --max-seconds 5 --interval 1 >/dev/null 2>&1
PASS_RC=$?
if [ "$PASS_RC" -eq 0 ]; then
  pass "T2: immediate pass exits 0 (got $PASS_RC)"
else
  fail "T2: immediate pass exits 0 (got $PASS_RC)"
fi

# ── T3: immediate fail exits 1 ──────────────────────────────────────────────
bash "$GATE_WAIT" cmd 'echo BROKEN' --pass 'NEVER_MATCHES_XYZ' --fail 'BROKEN' \
  --max-seconds 5 --interval 1 >/dev/null 2>&1
FAIL_RC=$?
if [ "$FAIL_RC" -eq 1 ]; then
  pass "T3: immediate fail exits 1 (got $FAIL_RC)"
else
  fail "T3: immediate fail exits 1 (got $FAIL_RC)"
fi

# ── T4 + T5: hanging inner command is BOUNDED, and does not orphan ─────────
# A marker file the backgrounded `sleep 10` touches AFTER it wakes, so we
# can tell whether it was actually killed (file absent) vs. merely
# abandoned-but-still-running (file would appear ~10s later).
MARKER_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t gate-wait-test)
trap 'rm -rf "$MARKER_DIR"' EXIT
MARKER_FILE="$MARKER_DIR/survived"

T4_START=$(date +%s)
bash "$GATE_WAIT" cmd "sleep 10 && touch '$MARKER_FILE'" --pass 'x' --fail 'y' \
  --max-seconds 1 --interval 1 >/dev/null 2>&1
T4_RC=$?
T4_END=$(date +%s)
T4_ELAPSED=$((T4_END - T4_START))

if [ "$T4_RC" -eq 2 ]; then
  pass "T4: hanging command (sleep 10, cap 1) returns PENDING/exit 2 (got $T4_RC)"
else
  fail "T4: hanging command (sleep 10, cap 1) returns PENDING/exit 2 (got $T4_RC)"
fi

if [ "$T4_ELAPSED" -le 5 ]; then
  pass "T4b: bounded within ~3s, not ~10s (elapsed ${T4_ELAPSED}s)"
else
  fail "T4b: bounded within ~3s, not ~10s (elapsed ${T4_ELAPSED}s — did NOT bound the inner call)"
fi

# Give a real, non-killed sleep every chance to have finished and touched
# the marker (it would if run_capped failed to kill it) before we check.
sleep 10
if [ -f "$MARKER_FILE" ]; then
  fail "T5: killed inner command does not survive as orphan (marker file WAS created — sleep 10 kept running)"
else
  pass "T5: killed inner command does not survive as orphan (marker file absent)"
fi

echo
echo "gate-wait.sh tests: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  printf 'FAILURES:\n'
  for m in "${FAIL_MSGS[@]}"; do printf '  - %s\n' "$m"; done
  exit 1
fi
exit 0

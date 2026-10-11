#!/usr/bin/env bash
# =============================================================================
# planted-bad.sh — the planted-bad controls for the U8 proofs
# -----------------------------------------------------------------------------
# 75-drama-song-ad-factory/mini-app/approvals/prove/planted-bad.sh
#
# Proves that the CLEAN control (approvals.prove.mjs) can actually FAIL. For
# each of the four behaviours it copies the approvals layer to a LOCAL temp
# copy, plants ONE defect that removes that behaviour's guard, runs the prover
# there, and requires it to go RED (exit 2) with the MATCHING case named FAIL.
# The shipped source is never touched; the temp copy is discarded and the clean
# run is re-asserted GREEN (exit 0) at the end.
#
#   bash 75-drama-song-ad-factory/mini-app/approvals/prove/planted-bad.sh
#
# Exit codes: 0 = every planted defect went red AND the clean run is green;
#             2 = a plant did not fail as it must, or the clean run is not green.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/.." && pwd)"          # .../approvals
PROVER="prove/approvals.prove.mjs"

fail=0
say() { printf '%s\n' "$*"; }

# run_prover <dir> -> prints output, returns the prover's exit code
run_prover() { ( cd "$1" && node "$PROVER" ) ; }

# plant <guard-token> <expected-failing-case> <label>
plant() {
  local guard="$1" want_case="$2" label="$3"
  local tmp; tmp="$(mktemp -d)"
  cp -R "$SRC"/. "$tmp/"

  # Replace the single guarded line with a syntactically-valid no-op.
  # The guard token lives only on that one line in approvals.mjs.
  if ! grep -q "U8-GUARD:${guard}" "$tmp/approvals.mjs"; then
    say "SETUP FAIL ${label}: guard token U8-GUARD:${guard} not found"
    rm -rf "$tmp"; fail=1; return
  fi
  sed -i.bak "s@.*U8-GUARD:${guard}.*@/* planted-bad: guard removed */@" "$tmp/approvals.mjs"
  rm -f "$tmp/approvals.mjs.bak"
  if grep -q "U8-GUARD:${guard}" "$tmp/approvals.mjs"; then
    say "SETUP FAIL ${label}: mutation did not take"
    rm -rf "$tmp"; fail=1; return
  fi

  local out rc; out="$(run_prover "$tmp")"; rc=$?
  rm -rf "$tmp"

  if [ "$rc" -ne 2 ]; then
    say "RED FAIL ${label}: planted defect did not fail (exit ${rc}, want 2)"
    say "$out"
    fail=1; return
  fi
  if ! printf '%s\n' "$out" | grep -q "FAIL ${want_case} "; then
    say "RED FAIL ${label}: exited 2 but ${want_case} was not the failing case"
    say "$out"
    fail=1; return
  fi
  say "RED OK   ${label}: ${want_case} went red (exit 2) with the defect planted"
}

say "=== planted-bad controls ==============================================="
plant "version-dedup"    "C2_VERSION_DEDUP"               "C2 version dedup"
plant "first-answer-wins" "C1_FIRST_ANSWER_WINS"          "C1 first answer wins"
plant "escalation-cap"   "C3_NUDGE_REMINDER_SILENCE"      "C3 nudge/reminder/silence"
plant "producer-refuse"  "C4_PRODUCER_HANDOFF_REFUSES"    "C4 producer hand-off refuses"

say "=== clean control ====================================================="
out="$(run_prover "$SRC")"; rc=$?
say "$out"
if [ "$rc" -ne 0 ]; then
  say "GREEN FAIL: the clean run is not green (exit ${rc}, want 0)"
  fail=1
else
  say "GREEN OK : the clean run is green (exit 0)"
fi

say "======================================================================="
if [ "$fail" -ne 0 ]; then say "PLANTED-BAD SUITE FAILED"; exit 2; fi
say "PLANTED-BAD SUITE OK: every planted defect went red, the clean run is green"
exit 0

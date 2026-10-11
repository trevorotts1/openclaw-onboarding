#!/usr/bin/env bash
# =============================================================================
# planted-bad.sh — the planted-bad controls for the U20 prover
# -----------------------------------------------------------------------------
# 75-drama-song-ad-factory/mini-app/service/prove/planted-bad.sh
#
# Proves the CLEAN control (prove_push_optional.mjs) can actually FAIL. For each
# guarded behaviour it copies the whole mini-app to a LOCAL temp copy, plants ONE
# defect that removes that behaviour's guard, runs the prover there, and requires
# it to go RED (exit 2) with the MATCHING case named FAIL. The shipped source is
# never touched; the temp copy is discarded and the clean run is re-asserted
# GREEN (exit 0) at the end.
#
#   bash 75-drama-song-ad-factory/mini-app/service/prove/planted-bad.sh
#
# Exit codes: 0 = every planted defect went red AND the clean run is green;
#             2 = a plant did not fail as it must, or the clean run is not green.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$(cd "$HERE/../.." && pwd)"          # .../mini-app  (holds service/ and ui/)
PROVER="prove/prove_push_optional.mjs"

fail=0
say() { printf '%s\n' "$*"; }

run_prover() { ( cd "$1/service" && node "$PROVER" ) ; }

# plant <guard-token> <expected-failing-case> <label> <file-relative-to-mini-app>
plant() {
  local guard="$1" want_case="$2" label="$3" file="$4"
  local tmp; tmp="$(mktemp -d)"
  cp -R "$SRC"/. "$tmp/"

  # The guard token lives only on its one line and that line is a COMPLETE
  # statement, so replacing it with a comment leaves valid syntax that no longer
  # guards anything.
  if ! grep -q "U20-GUARD:${guard}" "$tmp/$file"; then
    say "SETUP FAIL ${label}: guard token U20-GUARD:${guard} not found in ${file}"
    rm -rf "$tmp"; fail=1; return
  fi
  sed -i.bak "s@.*U20-GUARD:${guard}.*@/* planted-bad: guard removed */@" "$tmp/$file"
  rm -f "$tmp/$file.bak"
  if grep -q "U20-GUARD:${guard}" "$tmp/$file"; then
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
plant "default-off"          "P1_OFF_BY_DEFAULT"            "P1 off by default"          "service/src/push.js"
plant "refuse-unconfigured"  "P3_SEND_REFUSES_UNCONFIGURED" "P3 send refuses unconfigured" "service/src/push.js"
plant "owns"                 "P5_ISOLATION"                 "P5 per-client isolation"    "service/src/push.js"
plant "ui-off"               "U20_UI_OFF_BY_DEFAULT"        "UI surface off by default"  "ui/push.js"

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

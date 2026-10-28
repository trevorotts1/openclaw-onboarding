#!/usr/bin/env bash
# qc-skip-count.test.sh - proves the QC SUMMARY's SKIP number matches the number
# of [SKIP] lines the checklist actually printed.
#
# The defect this pins: 11-run-qc-checklist.sh printed 15 [SKIP] lines from bare
# `echo "  [SKIP] ..."` sites that never touched the SKIP counter, so the summary
# under-reported (bare box: 14 printed vs "SKIP: 3"). Every emission must now go
# through report_skip, which prints AND increments once.
#
# Two independent checks:
#   (a) static  - no bare `echo "  [SKIP]` survives outside the report_skip helper;
#   (b) dynamic - run the real checklist against an empty HOME and require
#                 printed [SKIP] count == the "SKIP:" number in QC SUMMARY.
#
# Exit 0 = every assertion passes; 1 = a failure.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKLIST="$SCRIPT_DIR/11-run-qc-checklist.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); printf '  [PASS] %s\n' "$1"; }
bad() { FAIL=$((FAIL+1)); printf '  [FAIL] %s\n' "$1"; }

[ -f "$CHECKLIST" ] || { echo "FATAL: $CHECKLIST not found"; exit 2; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/qc-skip-count.XXXXXX")" || { echo "FATAL: mktemp failed"; exit 2; }
trap 'rm -rf "$TMP"' EXIT

# ===========================================================================
echo ""
echo "=== (a) static: every [SKIP] emission goes through report_skip =========="
# The single legitimate raw emitter is the report_skip helper itself.
BARE="$(grep -n 'echo "  \[SKIP\]' "$CHECKLIST" | grep -v 'report_skip()' || true)"
if [ -z "$BARE" ]; then
  ok "no bare 'echo \"  [SKIP]\"' site outside the report_skip helper"
else
  bad "bare [SKIP] echo site(s) bypass the counter:"
  printf '%s\n' "$BARE" | sed 's/^/        /'
fi

# Every line that mentions [SKIP] must be the helper definition or a report_skip call.
STRAY="$(grep -n '\[SKIP\]' "$CHECKLIST" | grep -v 'report_skip()' | grep -v 'report_skip "' || true)"
if [ -z "$STRAY" ]; then
  ok "every other [SKIP] mention is a report_skip call"
else
  bad "unaccounted [SKIP] mention(s):"
  printf '%s\n' "$STRAY" | sed 's/^/        /'
fi

# ===========================================================================
echo ""
echo "=== (b) dynamic: printed [SKIP] lines == QC SUMMARY 'SKIP:' ============="
EMPTY_HOME="$TMP/home"
mkdir -p "$EMPTY_HOME"
OUT="$TMP/out.txt"
ERR="$TMP/err.txt"

# Bare box: empty HOME, no PUBLIC_HOSTNAME/ROUTE_ID/MASTER_FILES_DIR, no openclaw.
env -i HOME="$EMPTY_HOME" PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  TMPDIR="$TMP" PUBLIC_HOSTNAME= ROUTE_ID= MASTER_FILES_DIR= \
  bash "$CHECKLIST" > "$OUT" 2> "$ERR"
RUN_RC=$?

PRINTED="$(grep -c '\[SKIP\]' "$OUT" || true)"
SUMMARY="$(grep -E '^  SKIP: [0-9]+' "$OUT" | head -1 | sed -E 's/^  SKIP: ([0-9]+).*/\1/' || true)"

if [ -z "$SUMMARY" ]; then
  bad "QC SUMMARY never printed a 'SKIP: <n>' line (run rc=$RUN_RC); tail of stderr:"
  tail -5 "$ERR" | sed 's/^/        /'
elif [ "$PRINTED" = "$SUMMARY" ]; then
  ok "printed [SKIP] lines ($PRINTED) == QC SUMMARY SKIP ($SUMMARY) [run rc=$RUN_RC]"
else
  bad "QC SUMMARY under-reports: printed [SKIP] lines=$PRINTED but summary SKIP=$SUMMARY [run rc=$RUN_RC]"
fi

if [ "${PRINTED:-0}" -gt 0 ]; then
  ok "the fixture actually exercised the skip paths ($PRINTED emissions) - not a vacuous pass"
else
  bad "fixture produced zero [SKIP] lines, so the equality above proves nothing"
fi

# ===========================================================================
echo ""
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: FAIL - [SKIP] emissions and the QC SUMMARY SKIP counter disagree."
  exit 1
fi
echo "RESULT: PASS - every [SKIP] emission increments SKIP exactly once."
exit 0

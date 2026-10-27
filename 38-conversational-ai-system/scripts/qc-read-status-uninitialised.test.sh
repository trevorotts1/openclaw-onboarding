#!/usr/bin/env bash
# qc-read-status-uninitialised.test.sh - proves 11-run-qc-checklist.sh tells three
# outcomes apart instead of collapsing them:
#
#   * UNINITIALISED with 0 failures (the gates' NOTHING-TO-CHECK path on a bare
#     box) is ACCEPTED and reported as SKIP - not a pass, not a failure;
#   * FAIL is still RED;
#   * malformed JSON and a MISSING file are still RED;
#   * PASS with 0 failures is still GREEN.
#
# The reader (QC_READ_STATUS) and the single disposition decision point
# (QC_STATUS_DISPOSITION) are extracted verbatim from the real checklist, so this
# suite fails if someone "fixes" the defect by making everything green.
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

extract_block() {
  awk -v start="# >>> $1" -v end="# <<< $1" '
    $0 == start { inblock = 1; next }
    $0 == end   { inblock = 0; next }
    inblock     { print }
  ' "$CHECKLIST"
}

READ_BLOCK="$(extract_block QC_READ_STATUS)"
DISP_BLOCK="$(extract_block QC_STATUS_DISPOSITION)"
if [ -z "$READ_BLOCK" ] || [ -z "$DISP_BLOCK" ]; then
  echo "FATAL: could not extract QC_READ_STATUS / QC_STATUS_DISPOSITION from $CHECKLIST"
  exit 2
fi

# --- reporter stubs: the disposition function's contract is which reporter it
# --- calls, so counting them is exactly how "red" is recognised here. ---------
P=0; F=0; M=0; S=0; LEGACY_CALLS=0
report_pass()    { P=$((P+1)); }
report_fail()    { F=$((F+1)); }
report_migrate() { M=$((M+1)); }
report_skip()    { S=$((S+1)); }
qc_record_legacy() { LEGACY_CALLS=$((LEGACY_CALLS+1)); }

reset_state() {
  P=0; F=0; M=0; S=0; LEGACY_CALLS=0
  QC_ST_LEGACY=""; QC_ST_FAILS=""; QC_ST_VERDICT=""; QC_ST_FILES=""; QC_ST_DIR=""
  QC_LEGACY_MAX=0; QC_LEGACY_SEEN=""; QC_MIGRATION_DIR=""
}

eval "$READ_BLOCK"
eval "$DISP_BLOCK"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

read_status() {  # $1 = status file; sets RS_RC
  RS_RC=0
  qc_read_status "$1" || RS_RC=$?
  return 0
}

status_file() {  # $1 = path, $2 = new_style_failures, $3 = verdict
  printf '%s\n' "{\"gate\":\"fixture\",\"legacy_needs_migration\":0,\"new_style_failures\":$2,\"verdict\":\"$3\",\"legacy_files\":[],\"workflows_dir\":\"\"}" > "$1"
}

# ===========================================================================
echo ""
echo "=== (a) UNINITIALISED, 0 failures -> ACCEPTED, section NOT red ==========="
reset_state
status_file "$TMP/uninitialised.json" 0 UNINITIALISED
read_status "$TMP/uninitialised.json"
if [ "$RS_RC" -eq 0 ] && [ "$QC_ST_VERDICT" = "UNINITIALISED" ]; then
  ok "qc_read_status accepts a well-formed UNINITIALISED status file (rc=0, verdict=$QC_ST_VERDICT)"
else
  bad "qc_read_status rejected a well-formed UNINITIALISED status file (rc=$RS_RC, verdict=${QC_ST_VERDICT:-<unset>})"
fi
reset_state
status_file "$TMP/uninitialised.json" 0 UNINITIALISED
read_status "$TMP/uninitialised.json"
if [ "$RS_RC" -eq 0 ]; then
  qc_report_disposition "qc-tool-gating" "pass text"
  if [ "$F" -eq 0 ] && [ "$P" -eq 0 ] && [ "$S" -eq 1 ]; then
    ok "disposition reports SKIP: 0 failures, 0 passes, 1 skip -> section not red"
  else
    bad "disposition of UNINITIALISED was not a clean skip (pass=$P fail=$F skip=$S)"
  fi
else
  bad "cannot exercise disposition: UNINITIALISED was rejected (rc=$RS_RC)"
fi

# ===========================================================================
echo ""
echo "=== (b) FAIL with failures > 0 -> still RED ============================="
reset_state
status_file "$TMP/fail.json" 3 FAIL
read_status "$TMP/fail.json"
if [ "$RS_RC" -eq 0 ] && [ "$QC_ST_VERDICT" = "FAIL" ]; then
  qc_report_disposition "qc-tool-gating" "pass text"
  if [ "$F" -eq 1 ] && [ "$S" -eq 0 ] && [ "$P" -eq 0 ]; then
    ok "well-formed FAIL file is RED (1 fail reported, no skip)"
  else
    bad "well-formed FAIL file did not turn the section red (pass=$P fail=$F skip=$S)"
  fi
else
  bad "qc_read_status did not surface the FAIL verdict (rc=$RS_RC, verdict=${QC_ST_VERDICT:-<unset>})"
fi

# ===========================================================================
echo ""
echo "=== (c) malformed JSON -> still RED ====================================="
reset_state
printf '%s\n' '{"gate":"fixture","legacy_needs_migration":0,' > "$TMP/bad.json"
read_status "$TMP/bad.json"
if [ "$RS_RC" -ne 0 ]; then
  ok "malformed JSON is rejected (rc=$RS_RC) -> the caller's report_fail path, red"
else
  bad "malformed JSON was accepted (rc=0, verdict=${QC_ST_VERDICT:-<unset>}) - the checklist has gone blind"
fi

# ===========================================================================
echo ""
echo "=== (d) missing status file -> still RED ================================"
reset_state
read_status "$TMP/does-not-exist.json"
if [ "$RS_RC" -ne 0 ]; then
  ok "a missing status file is rejected (rc=$RS_RC) -> red"
else
  bad "a missing status file was accepted (rc=0) - absent status must never pass"
fi

# ===========================================================================
echo ""
echo "=== (e) PASS with 0 failures -> still GREEN ============================="
reset_state
status_file "$TMP/pass.json" 0 PASS
read_status "$TMP/pass.json"
if [ "$RS_RC" -eq 0 ] && [ "$QC_ST_VERDICT" = "PASS" ]; then
  qc_report_disposition "qc-tool-gating" "pass text"
  if [ "$P" -eq 1 ] && [ "$F" -eq 0 ] && [ "$S" -eq 0 ]; then
    ok "PASS file stays GREEN (1 pass, 0 fail, 0 skip)"
  else
    bad "PASS file was not green (pass=$P fail=$F skip=$S)"
  fi
else
  bad "qc_read_status rejected a well-formed PASS file (rc=$RS_RC, verdict=${QC_ST_VERDICT:-<unset>})"
fi

# ===========================================================================
echo ""
echo "=== (f) UNINITIALISED carrying failures -> contradictory, still RED ====="
reset_state
status_file "$TMP/uninit-fails.json" 2 UNINITIALISED
read_status "$TMP/uninit-fails.json"
if [ "$RS_RC" -ne 0 ]; then
  ok "UNINITIALISED with failures>0 is rejected (rc=$RS_RC) -> red, never a silent skip"
else
  bad "UNINITIALISED with failures>0 was accepted -> a failing gate could be skipped away"
fi

# ===========================================================================
echo ""
echo "=== (g) unknown verdict -> still RED ==================================="
reset_state
status_file "$TMP/unknown-verdict.json" 0 GREEN
read_status "$TMP/unknown-verdict.json"
if [ "$RS_RC" -ne 0 ]; then
  ok "an unknown verdict is rejected (rc=$RS_RC) -> red"
else
  bad "an unknown verdict was accepted - the reader's whitelist has gone blind"
fi

# ===========================================================================
echo ""
echo "=== (h) the checklist actually routes all four status gates through it =="
MISSING=""
for gate in qc-playbook-doc qc-tool-gating qc-workflow-exits qc-playbook-declares; do
  n="$(grep -c "qc_report_disposition \"$gate\"" "$CHECKLIST" 2>/dev/null || true)"
  [ "$n" -eq 1 ] || MISSING="$MISSING $gate(count=$n)"
done
if [ -z "$MISSING" ]; then
  ok "qc-playbook-doc, qc-tool-gating, qc-workflow-exits and qc-playbook-declares each call qc_report_disposition exactly once"
else
  bad "status gate(s) not routed through the single disposition point:$MISSING"
fi

# ===========================================================================
echo ""
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo "RESULT: FAIL - the checklist still collapses real failure and nothing-to-check."
  exit 1
fi
echo "RESULT: PASS - UNINITIALISED skips, FAIL/malformed/missing stay red, PASS stays green."
exit 0

#!/usr/bin/env bash
# tests/rescue/RRX-TRIAGE/test_step6_log_read.sh
# ---------------------------------------------------------------------------
# RRX-123 — STEP 6 of the triage ladder READS the structured log.
#
# The old code ran `hits="$(grep -c -E ... "$todays_log" 2>/dev/null || echo 0)"`
# which had two defects:
#   * an UNREADABLE log (permissions, I/O) became 0 markers -> CLEAN, a false
#     pass for exactly the wedge signature the step exists to find;
#   * when nothing matched, `grep -c` printed "0" AND exited 1, so `|| echo 0`
#     appended a second "0" -> hits was "0\n0", which is not a number. The
#     detail then spanned two lines and the whole record was unparseable.
# The step now reads the log in python3, counts marker lines, and answers
# UNDETERMINED when the log cannot be read. Unknown never becomes clean.
#
# Method mirrors tests/unit/rr029-triage-qc-cases.test.sh lines 46-67: drive the
# REAL step6 out of scripts/rr-triage.sh (--source-only, JSON_MODE=1), set
# OCD_LOG_DIR to a temporary folder AFTER ocd_init, and read the verdict from
# the FIRST line of RESULTS. No live box is touched; every case asserts the
# VERDICT and the exit code, not just "it ran".
# ---------------------------------------------------------------------------
set -u
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TRIAGE="$REPO_ROOT/scripts/rr-triage.sh"
DESCRIPTOR="$REPO_ROOT/shared-utils/oc-env-descriptor.sh"
[ -f "$TRIAGE" ] || { echo "FATAL: $TRIAGE not found"; exit 2; }
[ -f "$DESCRIPTOR" ] && export OC_ENV_DESCRIPTOR="$DESCRIPTOR"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d)"
trap 'chmod -R u+rwX "$WORK" 2>/dev/null; rm -rf "$WORK"' EXIT

# _drive6 <log-dir> -> "verdict|rc|bits|detail"
# OCD_LOG_DIR is assigned AFTER ocd_init so the step reads the fixture folder
# and can never fall back to the host's live log directory.
_drive6() {
  local logdir="$1"
  bash -c '
    . "$1" --source-only 2>/dev/null
    ocd_init; JSON_MODE=1; PROBLEM_BITS=0; UNDETERMINED_COUNT=0; RESULTS=""
    OCD_LOG_DIR="$2"
    step6; rc=$?
    # Field-splitting with awk would cut the detail at its first pipe, and a
    # detail legitimately contains pipes. Strip the two leading fields with
    # parameter expansion instead -- and read only the FIRST record line, so a
    # multi-line detail (the old defect) cannot be mistaken for a verdict.
    line="$(printf "%s\n" "$RESULTS" | head -1)"
    r1="${line#*|}"; r2="${r1#*|}"
    v="${r2%%|*}"; d="${r2#*|}"
    printf "%s|%s|%s|%s" "$v" "$rc" "$PROBLEM_BITS" "$d"
  ' _ "$TRIAGE" "$logdir"
}

verdict_of() { printf '%s' "${1%%|*}"; }
rc_of()      { local r="${1#*|}"; printf '%s' "${r%%|*}"; }
bits_of()    { local r="${1#*|*|}"; printf '%s' "${r%%|*}"; }
detail_of()  { printf '%s' "${1#*|*|*}"; }

LOG_NAME="openclaw-$(date +%Y-%m-%d).log"
echo "== [RRX-123] STEP 6 reads the structured log =="

# --- (a) NO FILE: nothing to read is UNDETERMINED, never CLEAN --------------
mkdir -p "$WORK/absent"
r="$(_drive6 "$WORK/absent")"
if [ "$(verdict_of "$r")" = "UNDETERMINED" ] && [ "$(rc_of "$r")" -ne 0 ]; then
  ok "no log file -> UNDETERMINED"
else
  bad "no log file produced $(verdict_of "$r") rc=$(rc_of "$r")"
fi

# --- (b) NO MARKER LINE: CLEAN, and the detail says 0 on the FIRST line -----
# The old code printed "0\n0" here: the detail spanned two lines and the record
# could not be parsed. Asserting the verdict alone would pass on the old code,
# so the first-line detail is asserted too.
mkdir -p "$WORK/plain"
printf 'starting gateway\nordinary chatter\nnothing to see\n' > "$WORK/plain/$LOG_NAME"
r="$(_drive6 "$WORK/plain")"
if [ "$(verdict_of "$r")" = "CLEAN" ] && [ "$(rc_of "$r")" -eq 0 ]; then
  ok "log with no marker line -> CLEAN, exit 0"
else
  bad "clean log produced $(verdict_of "$r") rc=$(rc_of "$r")"
fi
case "$(detail_of "$r")" in
  *"0 compaction-failure marker(s)"*) ok "detail carries '0 compaction-failure marker(s)' on the first line" ;;
  *) bad "detail does not name zero markers: $(detail_of "$r")" ;;
esac

# --- (c) ONE MARKER: routine, below the 2+ wedge signature -> CLEAN ---------
mkdir -p "$WORK/one"
printf 'ok\ncontextEngine.compact() threw once\nmore chatter\n' > "$WORK/one/$LOG_NAME"
r="$(_drive6 "$WORK/one")"
if [ "$(verdict_of "$r")" = "CLEAN" ] && [ "$(rc_of "$r")" -eq 0 ]; then
  ok "one marker line -> CLEAN (one alone is routine)"
else
  bad "one marker produced $(verdict_of "$r") rc=$(rc_of "$r")"
fi

# --- (d) THREE MARKERS, one of each phrase -> PROBLEM, non-zero exit --------
mkdir -p "$WORK/three"
printf 'contextEngine.compact() threw\nCompaction timed out after 300s\ncould not recover this turn\n' > "$WORK/three/$LOG_NAME"
r="$(_drive6 "$WORK/three")"
if [ "$(verdict_of "$r")" = "PROBLEM" ] && [ "$(rc_of "$r")" -ne 0 ]; then
  ok "three markers (one of each phrase) -> PROBLEM, non-zero exit"
else
  bad "three markers produced $(verdict_of "$r") rc=$(rc_of "$r")"
fi
if [ $(( $(bits_of "$r") & 32 )) -ne 0 ]; then
  ok "three markers set the COMPACTION bit"
else
  bad "COMPACTION bit not set (bits=$(bits_of "$r"))"
fi

# --- (e) UNREADABLE LOG (mode 000): UNDETERMINED, never CLEAN --------------
# Skipped as root: root reads through the mode and the case would prove nothing.
if [ "$(id -u)" -eq 0 ]; then
  echo "  (unreadable-log case skipped -- running as root, mode 000 proves nothing)"
else
  mkdir -p "$WORK/noread"
  printf 'contextEngine.compact() threw\n' > "$WORK/noread/$LOG_NAME"
  chmod 000 "$WORK/noread/$LOG_NAME"
  r="$(_drive6 "$WORK/noread")"
  chmod 600 "$WORK/noread/$LOG_NAME"
  if [ "$(verdict_of "$r")" = "UNDETERMINED" ] && [ "$(rc_of "$r")" -ne 0 ]; then
    ok "unreadable log (mode 000) -> UNDETERMINED, not CLEAN"
  else
    bad "unreadable log produced $(verdict_of "$r") rc=$(rc_of "$r") (the old code answered CLEAN)"
  fi
fi

echo "[test_step6_log_read] PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
echo "[test_step6_log_read] PASS (RRX-123 step 6 log read)"
exit 0

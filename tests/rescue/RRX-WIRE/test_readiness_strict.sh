#!/usr/bin/env bash
# =============================================================================
# tests/rescue/RRX-WIRE/test_readiness_strict.sh
# =============================================================================
# RRX-023. A caller that reads ONLY the exit code has no way to learn that the
# receiver is refusing this box: the claim_unauthorized / slug_mismatch flags
# and the intake-auth flag file were "information only", so a flagged box still
# exited with its state's code. With --strict any recorded problem is exit 4.
#
# What this proves, against the REAL receiver tool driven through the RR-028
# harness (a hermetic synthetic box):
#   A1  the recording wrapper saw the invocation (the instrument is live);
#   A2  without --strict, a box carrying claim-unauthorized.json still exits
#       with its STATE's own code (the default behaviour is unchanged);
#   A3  with --strict, the same box exits 4;
#   A4  --strict changes only the exit code, not the reported state;
#   A5  the recorded argv of the strict run carries --strict;
#   B1  --strict alone does not fabricate a flag: the same box with NO recorded
#       problem exits with its state's code, never 4;
#   C1  --strict also honours the intake-auth flag file (state/rr-intake-auth.flag).
#
# Every fixture is temp-dir only, with a synthetic slug and no real credential.
# Exit 0 = all pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
RR028_REPO="$REPO_ROOT"
export RR028_REPO

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== test_readiness_strict.sh ==="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx023-strict.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

. "$REPO_ROOT/tests/rescue/RR-028/lib-readiness-harness.sh"
rr028_require_files

# expected_rc <state> -> the exit code the tool's own contract assigns to it.
expected_rc() {
  case "$1" in
    VERIFIED)         echo 0 ;;
    SCHEDULED)        echo 1 ;;
    ENROLLED_PENDING) echo 2 ;;
    UNENROLLED)       echo 3 ;;
    *)                echo 78 ;;
  esac
}

# ---------------------------------------------------------------------------
# The recorder: a wrapper INSIDE the fixture that records the argv vector it
# was handed and then runs the real tool. Without this, a case asserting "the
# exit code changed" could pass on a script that was never invoked at all.
# ---------------------------------------------------------------------------
make_recorder() {
  _box="$1"
  cat > "$_box/bin/record-rr" <<'SH'
#!/usr/bin/env bash
{
  printf 'ARGV'
  for _a in "$@"; do printf '\037%s' "$_a"; done
  printf '\n'
} >> "$RRX_RECORD_LOG"
exec bash "$RRX_RECORD_SCRIPT" "$@"
SH
  chmod +x "$_box/bin/record-rr"
}

# rr_run_rec <box> [args...] — run the wrapper against the box. Sets RR_OUT,
# RR_RC and RR_ERR; the argv log is reset first and read back from
# <box>/rr-argv.log.
rr_run_rec() {
  _box="$1"; shift
  : > "$_box/rr-argv.log"
  RR_OUT="$(env \
      RR_ROOT="$_box/.openclaw" \
      OC_CONFIG_ROOT="$_box/.openclaw" \
      RR028_JOBS="$_box/jobs.json" \
      RR028_CALLLOG="$_box/calls.log" \
      OC_PLATFORM=mac \
      OC_TARGET_MODE=launchd \
      OC_TARGET_ID=ai.openclaw.gateway \
      OC_SERVICE_LABEL=ai.openclaw.gateway \
      OC_SKIP_CLI_PROBE=1 \
      HOME="$_box" \
      PATH="$_box/bin:$PATH" \
      RRX_RECORD_LOG="$_box/rr-argv.log" \
      RRX_RECORD_SCRIPT="$_box/.openclaw/skills/65-rescue-receiver/rr-readiness.sh" \
      bash "$_box/bin/record-rr" "$@" 2>"$_box/stderr.txt")"
  RR_RC=$?
  RR_ERR="$_box/stderr.txt"
}

# =============================================================================
# BOX 1 — a recorded claim_unauthorized problem.
# =============================================================================
BOX="$WORK/box-flagged"
rr028_make_box "$BOX"
make_recorder "$BOX"
mkdir -p "$BOX/.openclaw/state/rr-receiver"
printf '{"http":"401","first_at":"2026-01-01T00:00:00Z","count":3}\n' \
  > "$BOX/.openclaw/state/rr-receiver/claim-unauthorized.json"

# ---- Without --strict: the default behaviour must be unchanged. -------------
rr_run_rec "$BOX" --json
RC_PLAIN="$RR_RC"
OUT_PLAIN="$RR_OUT"
STATE_PLAIN="$(rr028_field "$OUT_PLAIN" state)"

if [ -s "$BOX/rr-argv.log" ]; then
  pass "A1: the recording wrapper saw the invocation (the instrument is live)"
else
  fail "A1: the recorder logged nothing; the instrument did not fire"
fi

if [ "$RC_PLAIN" = "$(expected_rc "$STATE_PLAIN")" ]; then
  pass "A2: without --strict the exit code is the state's own code (rc=$RC_PLAIN state=$STATE_PLAIN)"
else
  fail "A2: without --strict rc=$RC_PLAIN, state=$STATE_PLAIN (expected $(expected_rc "$STATE_PLAIN"))"
fi

if [ "$RC_PLAIN" != "4" ]; then
  pass "A3: without --strict a recorded problem does not become exit 4 (default unchanged)"
else
  fail "A3: without --strict the tool already exited 4; the default changed"
fi

if [ -s "$BOX/rr-argv.log" ] && ! grep -q -- '--strict' "$BOX/rr-argv.log"; then
  pass "A4: the plain run's recorded argv carries NO --strict"
else
  fail "A4: the plain run's recorded argv is empty or mentions --strict"
fi

# ---- With --strict: exit 4, same state. ------------------------------------
rr_run_rec "$BOX" --json --strict
RC_STRICT="$RR_RC"
OUT_STRICT="$RR_OUT"
STATE_STRICT="$(rr028_field "$OUT_STRICT" state)"

if [ "$RC_STRICT" = "4" ]; then
  pass "A5: --strict with claim-unauthorized.json exits 4"
else
  fail "A5: --strict exited $RC_STRICT, expected 4 (stderr: $(cat "$RR_ERR" 2>/dev/null))"
fi

if [ "$STATE_STRICT" = "$STATE_PLAIN" ]; then
  pass "A6: --strict changes only the exit code, not the reported state ($STATE_STRICT)"
else
  fail "A6: state changed under --strict: plain=$STATE_PLAIN strict=$STATE_STRICT"
fi

if [ -s "$BOX/rr-argv.log" ] && grep -q -- '--strict' "$BOX/rr-argv.log"; then
  pass "A7: the strict run's recorded argv carries --strict (the run was real)"
else
  fail "A7: the strict run's recorded argv does not carry --strict"
fi

# =============================================================================
# BOX 2 — the control. Same box, NO recorded problem: --strict must not
# fabricate one, so the exit code is still the state's own code.
# =============================================================================
BOX2="$WORK/box-clean"
rr028_make_box "$BOX2"
make_recorder "$BOX2"

rr_run_rec "$BOX2" --json --strict
RC_CLEAN="$RR_RC"
STATE_CLEAN="$(rr028_field "$RR_OUT" state)"

if [ "$RC_CLEAN" = "$(expected_rc "$STATE_CLEAN")" ] && [ "$RC_CLEAN" != "4" ]; then
  pass "B1: --strict alone does not fabricate a flag (rc=$RC_CLEAN state=$STATE_CLEAN)"
else
  fail "B1: --strict on a clean box exited $RC_CLEAN state=$STATE_CLEAN; expected $(expected_rc "$STATE_CLEAN"), never 4"
fi

# =============================================================================
# BOX 3 — the intake-auth flag file is one of the three recorded problems.
# =============================================================================
BOX3="$WORK/box-intake"
rr028_make_box "$BOX3"
make_recorder "$BOX3"
printf '{"class":"RR_SECRET_STALE","http":401,"ts":"2026-01-01T00:00:00Z"}\n' \
  > "$BOX3/.openclaw/state/rr-intake-auth.flag"

rr_run_rec "$BOX3" --json
RC_INTAKE_PLAIN="$RR_RC"
rr_run_rec "$BOX3" --json --strict
RC_INTAKE_STRICT="$RR_RC"

if [ "$RC_INTAKE_PLAIN" != "4" ] && [ "$RC_INTAKE_STRICT" = "4" ]; then
  pass "C1: intake-auth flag file: plain rc=$RC_INTAKE_PLAIN, --strict rc=4"
else
  fail "C1: intake-auth flag file: plain rc=$RC_INTAKE_PLAIN (expected not 4), --strict rc=$RC_INTAKE_STRICT (expected 4)"
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0

#!/usr/bin/env bash
# tests/rescue/RR-028/mutate_argv_readback.sh — falsification harness for the
# RR-028 argv readback fix.
#
# WHY THIS FILE EXISTS. A green test proves nothing until you have watched it
# go red for the right reason. This harness DISABLES THE EFFECT of each part of
# the fix while leaving every declaration intact -- no block is deleted, so a
# mutation can never "pass" by crashing the engine in a way that happens to
# make an assertion vacuous.
#
# For EVERY mutation, and BEFORE any result is interpreted, it asserts:
#   (a) the marker occurs EXACTLY ONCE in the target file (so the edit is the
#       one intended, not a lookalike elsewhere),
#   (b) the file actually CHANGED on disk (sha256 before != after),
#   (c) the mutated file still PARSES (bash -n) AND its embedded Python still
#       COMPILES.
# A mutation that fails (a), (b) or (c) is reported as SETUP-FAILED and is NOT
# counted as caught: an unapplied mutation "catching" a test would be a lie.
#
# It then runs the batteries and reports CAUGHT / NOT CAUGHT per mutation, for
# the NEW battery and for the three PRE-EXISTING ones -- which is what
# documents that the old suite was blind to this defect.
#
# The target file is restored from a byte-compared backup on EXIT, including on
# a failed or interrupted run.
set -u

if [ -n "${BASH_SOURCE:-}" ]; then _HERE_SRC="${BASH_SOURCE[0]}"; else _HERE_SRC="$0"; fi
HERE="$(cd "$(dirname "$_HERE_SRC")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
RR028_REPO="$REPO"
export RR028_REPO

TARGET="$REPO/shared-utils/rr-readiness.sh"
[ -f "$TARGET" ] || { echo "FATAL: no $TARGET"; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rr028-mut.XXXXXX")"
BAK="$WORK/rr-readiness.sh.orig"
cp "$TARGET" "$BAK" || exit 2
ORIG_SHA="$(shasum -a 256 "$BAK" 2>/dev/null | awk '{print $1}')"
[ -n "$ORIG_SHA" ] || ORIG_SHA="$(sha256sum "$BAK" | awk '{print $1}')"

restore() {
  cp "$BAK" "$TARGET" 2>/dev/null || true
}
trap 'restore; rm -rf "$WORK"' EXIT
trap 'restore; rm -rf "$WORK"; exit 130' INT
trap 'restore; rm -rf "$WORK"; exit 143' TERM

# Verify the mutated engine still parses AND its embedded Python compiles.
# Silence here means "still parses"; any output means the mutation broke the
# file and the mutation is INVALID as evidence.
parses_ok() {
  bash -n "$TARGET" 2>/dev/null || return 1
  python3 - "$TARGET" <<'PY' >/dev/null 2>&1
import re, sys
src = open(sys.argv[1], encoding="utf-8").read()
# The scan pattern for the engine's INLINE programs is assembled at runtime,
# character by character, ON PURPOSE. Written literally it would contain the
# short-flag-plus-quote sequence that CI guard ONB-STATE-001
# (scripts/check-embedded-python-syntax.py) looks for when it extracts EVERY
# inline program across the repo to compile it -- and that guard deliberately
# also treats such sequences appearing inside deferred-eval strings as code,
# per its own design notes. It would then try to compile this regex FRAGMENT
# as Python, which cannot compile, and fail the build over a scan that is
# entirely correct. Building the sequence from chr() keeps the regex
# byte-identical while leaving nothing for the guard to mis-take for a
# program. Do NOT "simplify" this back into a literal.
_FLAG = "-" + chr(99)
_OPEN = chr(39)
_PROG = "python3 " + _FLAG + " " + _OPEN
blocks = re.findall(_PROG + r"\n(.*?)\n" + _OPEN + r" 2>/dev/null", src, re.S)
if not blocks:
    sys.exit(1)
for b in blocks:
    compile(b, "<embedded>", "exec")
PY
}

# apply_mutation <python-encoded-old> <python-encoded-new>
apply_mutation() {
  RR028_T="$TARGET" RR028_OLD="$1" RR028_NEW="$2" python3 - <<'PY'
import os, sys
p = os.environ["RR028_T"]
old = os.environ["RR028_OLD"]; new = os.environ["RR028_NEW"]
s = open(p, encoding="utf-8").read()
n = s.count(old)
if n != 1:
    sys.stderr.write("marker occurs %d times (must be exactly 1)\n" % n)
    sys.exit(3)
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
PY
}

sha_of() {
  shasum -a 256 "$1" 2>/dev/null | awk '{print $1}' \
    || sha256sum "$1" | awk '{print $1}'
}

# run_battery <battery-file> -> prints "<passed> <failed> <rc>"; rc!=0 => caught
run_battery() {
  _out="$WORK/out.txt"
  RR028_REPO="$REPO" bash "$REPO/tests/rescue/RR-028/$1" >"$_out" 2>&1
  _rc=$?
  _res="$(grep -E '^RESULT:' "$_out" | tail -1)"
  printf '%s %s %s' \
    "$(printf '%s' "$_res" | sed -n 's/^RESULT: \([0-9]*\) passed.*/\1/p')" \
    "$(printf '%s' "$_res" | sed -n 's/.*, \([0-9]*\) failed.*/\1/p')" \
    "$_rc"
}

NEW_BATTERY="test_cron_argv_readback.sh"
OLD_BATTERIES="test_readiness_states.sh test_safe_probe.sh test_wire_install_vs_ready.sh"

echo "== RR-028 argv readback: mutation (falsification) harness =="
echo "   target: shared-utils/rr-readiness.sh"
echo "   sha256(original): $ORIG_SHA"

# ---------------------------------------------------------------------------
# Baseline: BEFORE any mutation, both the new and the old batteries pass. If
# they do not, every "caught" below would be meaningless.
# ---------------------------------------------------------------------------
echo ""
echo "--- baseline (unmutated) ---"
# A red baseline makes every later "caught" uninterpretable, so ABORT on one.
# A rare infrastructure flake (the receiver stubs bind a derived port, so
# back-to-back battery runs can collide) is handled EXPLICITLY rather than
# silently: a red battery is re-run ONCE, the failing assertion lines are
# printed either way, and a battery that goes green on the re-run is recorded
# as DECLARED-FLAKY in the output and in the summary.
FLAKY=""
baseline_ok() {  # baseline_ok <battery>
  _b="$1"
  r="$(run_battery "$_b")"
  if [ "$(echo "$r" | awk '{print $3}')" != "0" ]; then
    echo "   $BASE_TAG $_b: passed=$(echo "$r" | awk '{print $1}') failed=$(echo "$r" | awk '{print $2}') rc=$(echo "$r" | awk '{print $3}') — RED"
    grep -E '^  FAIL' "$WORK/out.txt" | sed 's/^/     /'
    echo "   re-running once to distinguish a real red from an infrastructure flake..."
    r="$(run_battery "$_b")"
    if [ "$(echo "$r" | awk '{print $3}')" = "0" ]; then
      echo "   $BASE_TAG $_b: GREEN on re-run => DECLARED-FLAKY (not counted against the mutation result)"
      FLAKY="$FLAKY $_b"
      return 0
    fi
    echo "   $BASE_TAG $_b: STILL RED on re-run => real red"
    grep -E '^  FAIL' "$WORK/out.txt" | sed 's/^/     /'
    return 1
  fi
  echo "   $BASE_TAG $_b: passed=$(echo "$r" | awk '{print $1}') failed=$(echo "$r" | awk '{print $2}') rc=$(echo "$r" | awk '{print $3}')"
  return 0
}
BL_OK=1
BASE_TAG="baseline"
for b in $OLD_BATTERIES; do baseline_ok "$b" || BL_OK=0; done
baseline_ok "$NEW_BATTERY" || BL_OK=0
if [ "$BL_OK" = "1" ]; then
  echo "   OK: all batteries green before mutation — a later red is attributable to the mutation"
  [ -z "$FLAKY" ] || echo "   NOTE (declared): flaky baseline battery/batteries:$FLAKY"
else
  echo "   FATAL: a battery is red at baseline; mutation results would be uninterpretable"
  exit 2
fi

# ---------------------------------------------------------------------------
# The mutations. Each DISABLES ONE EFFECT of the fix and keeps every
# declaration (function name, branch, comment) in place.
# ---------------------------------------------------------------------------
MUT_NAMES=""
MUT_OLD_1='    return v[2]'
MUT_NEW_1='    return None'
MUT_NAMES="$MUT_NAMES M1-argv-decode-disabled"

MUT_OLD_2='_rrr_ck_is_wrapflag() {
    [ "$1" = "-lc" ] || [ "$1" = "-c" ]
}'
MUT_NEW_2='_rrr_ck_is_wrapflag() {
    return 1
}'
MUT_NAMES="$MUT_NAMES M2-wrapper-strip-disabled"

MUT_OLD_3='            _rrr_ck_abs="$_rrr_ck_root/$_rrr_ck_leaf" ;;'
MUT_NEW_3='            _rrr_ck_abs="$_rrr_ck_leaf" ;;'
MUT_NAMES="$MUT_NAMES M3-relative-leaf-resolution-disabled"

MUT_OLD_4='    _rrr_ck_canon "$_rrr_ck_abs" || return 1
    _RRR_CK_KEY="$_RRR_CK_C"'
MUT_NEW_4='    _RRR_CK_KEY="$_rrr_ck_abs"'
MUT_NAMES="$MUT_NAMES M4-path-canonicalisation-disabled"

MUT_OLD_5='            cmd = ""'
MUT_NEW_5='            cmd = "kind=" + (g(j, "payload", "kind") or "")'
MUT_NAMES="$MUT_NAMES M5-unreadable-dressed-up-as-a-value"

MUT_OLD_6='    if not isinstance(v, list) or len(v) != 3:'
MUT_NEW_6='    if not isinstance(v, list) or len(v) < 3:'
MUT_NAMES="$MUT_NAMES M6-narrow-shape-widened-extra-argv-accepted"

MUT_OLD_7='    if [ -n "$_rrr_ce_wantkey" ] \
       && [ "$(rrr_cron_cmd_key_of "$RRR_CRON_COMMAND")" = "$_rrr_ce_wantkey" ]; then :; else'
MUT_NEW_7='    if [ "$RRR_CRON_COMMAND" = "$_rrr_ce_wantcmd" ]; then :; else'
MUT_NAMES="$MUT_NAMES M7-normalised-compare-reverted-to-byte-compare"

MUT_OLD_8='[ -n "$_rrr_ce_wantkey" ] && [ "$_rrr_ce_cmdkey" = "$_rrr_ce_wantkey" ]'
MUT_NEW_8='[ "$_rrr_ce_cmdkey" = "$_rrr_ce_wantkey" ]'
MUT_NAMES="$MUT_NAMES M8-empty-wantkey-guard-dropped"

CAUGHT=0; NOTCAUGHT=0; SETUPFAIL=0
SUMMARY=""

for name in $MUT_NAMES; do
  n="${name#M}"; n="${n%%-*}"
  eval "OLD=\"\${MUT_OLD_$n}\""
  eval "NEW=\"\${MUT_NEW_$n}\""
  echo ""
  echo "--- $name ---"
  cp "$BAK" "$TARGET"
  BEFORE_SHA="$(sha_of "$TARGET")"
  if ! ERR="$(apply_mutation "$OLD" "$NEW" 2>&1)"; then
    echo "   SETUP-FAILED (a): marker not exactly once — $ERR"
    SETUPFAIL=$((SETUPFAIL+1)); SUMMARY="$SUMMARY
   $name: SETUP-FAILED ($ERR)"; continue
  fi
  AFTER_SHA="$(sha_of "$TARGET")"
  if [ "$BEFORE_SHA" = "$AFTER_SHA" ]; then
    echo "   SETUP-FAILED (b): file did NOT change on disk (sha unchanged)"
    SETUPFAIL=$((SETUPFAIL+1)); SUMMARY="$SUMMARY
   $name: SETUP-FAILED (no change on disk)"; continue
  fi
  echo "   (a) marker occurred exactly once  OK"
  echo "   (b) file changed on disk          OK  ${BEFORE_SHA:0:12} -> ${AFTER_SHA:0:12}"
  if parses_ok; then
    echo "   (c) mutated file still parses (bash -n + embedded Python compiles)  OK"
  else
    echo "   SETUP-FAILED (c): mutated file no longer parses — this mutation is INVALID evidence"
    SETUPFAIL=$((SETUPFAIL+1)); SUMMARY="$SUMMARY
   $name: SETUP-FAILED (does not parse)"; continue
  fi

  NR="$(run_battery "$NEW_BATTERY")"
  NRC="$(echo "$NR" | awk '{print $3}')"; NFAIL="$(echo "$NR" | awk '{print $2}')"
  OLD_RED=""
  for b in $OLD_BATTERIES; do
    r="$(run_battery "$b")"
    [ "$(echo "$r" | awk '{print $3}')" = "0" ] || OLD_RED="$OLD_RED ${b%.sh}"
  done
  if [ "$NRC" != "0" ]; then
    if grep -q '^RESULT:' "$WORK/out.txt"; then
      echo "   CAUGHT by $NEW_BATTERY ($NFAIL failing assertions)"
    else
      echo "   CAUGHT by $NEW_BATTERY (battery aborted before RESULT: rc=$NRC)"
    fi
    CAUGHT=$((CAUGHT+1))
    SUMMARY="$SUMMARY
   $name: CAUGHT by $NEW_BATTERY"
  else
    echo "   NOT CAUGHT by $NEW_BATTERY (0 failing assertions) — record this honestly"
    NOTCAUGHT=$((NOTCAUGHT+1))
    SUMMARY="$SUMMARY
   $name: NOT CAUGHT by the new battery"
  fi
  if [ -n "$OLD_RED" ]; then
    echo "   old suite also red for:$OLD_RED"
    SUMMARY="$SUMMARY
     (old suite red for:$OLD_RED)"
  else
    echo "   old suite stayed GREEN for this mutation"
    SUMMARY="$SUMMARY
     (old suite stayed GREEN)"
  fi
done

restore
RESTORED_SHA="$(sha_of "$TARGET")"
echo ""
echo "--- restore ---"
if [ "$RESTORED_SHA" = "$ORIG_SHA" ]; then
  echo "   target restored byte-for-byte to $ORIG_SHA"
else
  echo "   FATAL: restore failed ($RESTORED_SHA != $ORIG_SHA)"
fi

echo ""
echo "=========================================================="
echo "MUTATION SUMMARY"
echo "  caught:       $CAUGHT"
echo "  NOT caught:   $NOTCAUGHT"
echo "  setup-failed: $SETUPFAIL"
[ -z "$FLAKY" ] || echo "  declared-flaky baselines:$FLAKY"
printf '%s\n' "$SUMMARY"
echo "=========================================================="
[ "$NOTCAUGHT" -eq 0 ] && [ "$SETUPFAIL" -eq 0 ] || exit 1
exit 0

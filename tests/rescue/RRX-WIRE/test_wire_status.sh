#!/usr/bin/env bash
# =============================================================================
# tests/rescue/RRX-WIRE/test_wire_status.sh
# =============================================================================
# RRX-042. Every way the installer can finish is written to ONE small file,
# <openclaw root>/state/rr-receiver/wire-status.json, mode 0600:
#   {"schema":"rrx-042/wire-status/1","at":<epoch>,
#    "poll_registered":true|false|null,"reason":"<code>",
#    "escalation_section":true|false|null}
# rr-readiness.sh --json surfaces the parsed file under flags.wire, and with
# --strict a recorded poll_registered=false is a reason to return 4.
#
# What this proves, against the REAL wire.sh / rr-readiness.sh driven through
# the RR-028 harness (hermetic synthetic boxes, stub openclaw, no network):
#   (a) an UNENROLLED fixture leaves poll_registered false, reason not_enrolled,
#       and wire.sh still exits 0;
#   (b) an ENROLLED fixture whose stub CLI advertises NO full-status flag
#       (RR028_MOCK_NO_ALL=1) leaves poll_registered false and reason
#       visibility_insufficient, and wire.sh still exits 0;
#   (c) an ENROLLED fixture with the working stub leaves poll_registered true;
#   (d) rr-readiness.sh --json --strict on fixture (b) exits 4 and its JSON has
#       flags.wire.reason == visibility_insufficient.
#
# Every fixture is temp-dir only, with synthetic values and no real credential.
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

echo "=== test_wire_status.sh ==="

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rrx042-wire-status.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

. "$REPO_ROOT/tests/rescue/RR-028/lib-readiness-harness.sh"
rr028_require_files

WS_NAME="wire-status.json"

# ws_field <box> <key> — one field of the status file, JSON-encoded for
# non-strings; <UNREADABLE> when it cannot be parsed, <MISSING> when absent.
ws_field() {
  RRX_F="$2" python3 -c 'import json, os, sys
try:
    d = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    print("<UNREADABLE>"); sys.exit(0)
if not isinstance(d, dict) or os.environ["RRX_F"] not in d:
    print("<MISSING>"); sys.exit(0)
v = d[os.environ["RRX_F"]]
print(v if isinstance(v, str) else json.dumps(v))' "$1/.openclaw/state/rr-receiver/$WS_NAME"
}

# ws_mode <box> — the file's permission bits, e.g. 600.
ws_mode() {
  python3 -c 'import os, sys
print(oct(os.stat(sys.argv[1]).st_mode & 0o777)[2:])' \
    "$1/.openclaw/state/rr-receiver/$WS_NAME" 2>/dev/null
}

# =============================================================================
# (a) UNENROLLED: nothing to wire, but the reason is on the box.
# =============================================================================
echo "--- (a) unenrolled fixture ---"
BOXA="$WORK/box-unenrolled"
printf 'RR_RECEIVER_URL=http://127.0.0.1:1/rr\nRR_BOX_SLUG=box-synthetic\n' \
  > "$WORK/store-unenrolled.env"
rr028_make_box "$BOXA" "$WORK/store-unenrolled.env"
rr028_wire "$BOXA" >/dev/null 2>&1
RCA=$?

[ "$RCA" = "0" ] \
  && pass "A1: unenrolled wire.sh exits 0 (nothing failed, nothing claimed)" \
  || fail "A1: unenrolled wire.sh exited $RCA, expected 0"

if [ -f "$BOXA/.openclaw/state/rr-receiver/$WS_NAME" ]; then
  pass "A2: the status file exists at state/rr-receiver/$WS_NAME"
else
  fail "A2: no status file was written on the unenrolled path"
fi

[ "$(ws_field "$BOXA" poll_registered)" = "false" ] \
  && pass "A3: poll_registered is false" \
  || fail "A3: poll_registered is '$(ws_field "$BOXA" poll_registered)', expected false"
[ "$(ws_field "$BOXA" reason)" = "not_enrolled" ] \
  && pass "A4: reason is not_enrolled" \
  || fail "A4: reason is '$(ws_field "$BOXA" reason)', expected not_enrolled"
[ "$(ws_mode "$BOXA")" = "600" ] \
  && pass "A5: the file is mode 0600" \
  || fail "A5: the file mode is '$(ws_mode "$BOXA")', expected 600"
[ "$(ws_field "$BOXA" schema)" = "rrx-042/wire-status/1" ] \
  && pass "A6: the schema key carries the fixed contract string" \
  || fail "A6: schema is '$(ws_field "$BOXA" schema)'"
_es="$(ws_field "$BOXA" escalation_section)"
case "$_es" in
  true|false|null) pass "A7: escalation_section is true, false or null ($_es)" ;;
  *) fail "A7: escalation_section is '$_es'" ;;
esac

# =============================================================================
# (b) ENROLLED, but the stub CLI advertises no full-status flag: the readback
#     cannot prove the name free, so nothing is added and the installer still
#     exits 0 — while the box records that no poll job is proven.
# =============================================================================
echo "--- (b) enrolled, no full-status flag on the stub CLI ---"
BOXB="$WORK/box-noall"
rr028_make_box "$BOXB"
RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" rr028_wire "$BOXB" >/dev/null 2>&1
RCB=$?

[ "$RCB" = "0" ] \
  && pass "B1: the fail-closed refusal still exits 0 (nothing failed, nothing claimed)" \
  || fail "B1: wire.sh exited $RCB, expected 0"
[ "$(ws_field "$BOXB" poll_registered)" = "false" ] \
  && pass "B2: poll_registered is false" \
  || fail "B2: poll_registered is '$(ws_field "$BOXB" poll_registered)', expected false"
[ "$(ws_field "$BOXB" reason)" = "visibility_insufficient" ] \
  && pass "B3: reason is visibility_insufficient" \
  || fail "B3: reason is '$(ws_field "$BOXB" reason)', expected visibility_insufficient"
[ "$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8")).get("jobs") or []))' "$BOXB/jobs.json")" = "0" ] \
  && pass "B4: no poll job was added (the refusal mutated nothing)" \
  || fail "B4: a job appeared in the store despite the refusal"

# =============================================================================
# (c) ENROLLED with the working stub: the poll IS registered and read back.
# =============================================================================
echo "--- (c) enrolled with the working stub ---"
BOXC="$WORK/box-enrolled"
rr028_make_box "$BOXC"
rr028_wire "$BOXC" >/dev/null 2>&1
RCC=$?

[ "$RCC" = "0" ] \
  && pass "C1: enrolled wire.sh exits 0" \
  || fail "C1: enrolled wire.sh exited $RCC, expected 0"
[ "$(ws_field "$BOXC" poll_registered)" = "true" ] \
  && pass "C2: poll_registered is true" \
  || fail "C2: poll_registered is '$(ws_field "$BOXC" poll_registered)', expected true"
[ -n "$(ws_field "$BOXC" reason)" ] && [ "$(ws_field "$BOXC" reason)" != "<MISSING>" ] \
  && pass "C3: a reason code is recorded" \
  || fail "C3: no reason code was recorded"

# =============================================================================
# (d) rr-readiness.sh --json --strict on fixture (b): exit 4, and the parsed
#     installer record is visible at flags.wire.
# =============================================================================
echo "--- (d) --json --strict on fixture (b) ---"
RR028_EXTRA_ENV="RR028_MOCK_NO_ALL=1" rr028_readiness "$BOXB" --json --strict >/dev/null 2>&1
RCD=$?
JSON_D="$RR028_OUT"

[ "$RCD" = "4" ] \
  && pass "D1: rr-readiness.sh --json --strict exits 4" \
  || fail "D1: rr-readiness.sh exited $RCD, expected 4; output: $JSON_D"
[ "$(rr028_field "$JSON_D" flags.wire.reason)" = "visibility_insufficient" ] \
  && pass "D2: flags.wire.reason is visibility_insufficient" \
  || fail "D2: flags.wire.reason is '$(rr028_field "$JSON_D" flags.wire.reason)'"
[ "$(rr028_field "$JSON_D" flags.wire.poll_registered)" = "false" ] \
  && pass "D3: flags.wire.poll_registered is false" \
  || fail "D3: flags.wire.poll_registered is '$(rr028_field "$JSON_D" flags.wire.poll_registered)'"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0

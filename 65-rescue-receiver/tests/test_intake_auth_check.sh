#!/usr/bin/env bash
# =============================================================================
# 65-rescue-receiver/tests/test_intake_auth_check.sh
# =============================================================================
# Proves rr-intake-auth-check.sh classifies the RR escalation INTAKE correctly,
# and that it can never report a network problem as a stale credential.
#
# THE DEFECT: a box whose RESCUE_RANGERS_WEBHOOK_SECRET went stale after an
# operator-side rotation 401s silently for weeks. rr-readiness.sh probes only
# the RETURN leg, so a VERIFIED readiness report said nothing about whether the
# box could still get INTO the queue.
#
# Every case runs the REAL script against a REAL local HTTP responder, so the
# curl invocation, the 0600 header file and the request body are all exercised.
# The responder journals what it received, which is how the credential's route
# is proven rather than asserted.
#
# Exit 0 = all pass. Exit 1 = one or more failed.
# =============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
CHECK="$REPO_ROOT/65-rescue-receiver/rr-intake-auth-check.sh"
STUB="$HERE/stub-intake.py"

PASS=0; FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== test_intake_auth_check.sh ==="
[ -f "$CHECK" ] || { echo "  FAIL: $CHECK not found"; exit 1; }
[ -f "$STUB" ]  || { echo "  FAIL: $STUB not found"; exit 1; }

WORK="$(mktemp -d)"
STUB_PID=""
cleanup() {
  [ -n "$STUB_PID" ] && kill "$STUB_PID" 2>/dev/null
  rm -rf "$WORK"
}
trap cleanup EXIT

# The credential value used throughout. It must never appear in the flag file,
# in the request BODY, or in this script's own output.
FAKE_SECRET="fixture-not-a-real-secret-8f3a21"

# ---- Fixture box -------------------------------------------------------------
BOX="$WORK/box"
mkdir -p "$BOX/secrets" "$BOX/state"
FLAG="$BOX/state/rr-intake-auth.flag"
new_store() {  # new_store [secret]
  if [ "$#" -ge 1 ] && [ -n "$1" ]; then
    printf 'RESCUE_RANGERS_WEBHOOK_SECRET=%s\n' "$1" > "$BOX/secrets/.env"
  else
    printf '# no escalation credential on this box\n' > "$BOX/secrets/.env"
  fi
  chmod 600 "$BOX/secrets/.env"
}

# ---- Stub control ------------------------------------------------------------
JOURNAL="$WORK/journal.ndjson"
PORT=""
start_stub() {  # start_stub <mode>
  [ -n "$STUB_PID" ] && { kill "$STUB_PID" 2>/dev/null; wait "$STUB_PID" 2>/dev/null; STUB_PID=""; }
  : > "$JOURNAL"
  RR_STUB_MODE="$1" RR_STUB_JOURNAL="$JOURNAL" python3 "$STUB" > "$WORK/stub.out" 2>"$WORK/stub.err" &
  STUB_PID=$!
  PORT=""
  _i=0
  while [ "$_i" -lt 100 ]; do
    PORT="$(sed -n 's/^PORT \([0-9][0-9]*\)$/\1/p' "$WORK/stub.out" 2>/dev/null | head -1)"
    [ -n "$PORT" ] && break
    _i=$((_i + 1))
    sleep 0.05
  done
  [ -n "$PORT" ] || { echo "  FAIL: stub responder never bound a port"; exit 1; }
}

# run_check <url> -> sets OUT / RC
run_check() {
  OUT="$(RESCUE_RANGERS_WEBHOOK_URL="$1" \
        RESCUE_RANGERS_WEBHOOK_SECRET="" \
        RR_INTAKE_AUTH_TIMEOUT=15 \
        bash "$CHECK" --root "$BOX" 2>&1)"
  RC=$?
}

flag_class() { sed -n 's/.*"class"[[:space:]]*:[[:space:]]*"\([A-Z_]*\)".*/\1/p' "$FLAG" 2>/dev/null | head -1; }

# =============================================================================
# (1) OK — the intake answers test_suppressed
# =============================================================================
echo "--- (1) test_suppressed = OK ---"
new_store "$FAKE_SECRET"
printf '{"class":"RR_SECRET_STALE","http":403,"ts":"1970-01-01T00:00:00Z","remedy":"x"}\n' > "$FLAG"
start_stub suppressed
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 0 ] \
    && pass "1a: test_suppressed exits 0 (OK)" \
    || fail "1a: test_suppressed exited $RC, expected 0"
echo "$OUT" | grep -q "OK http=200" \
    && pass "1b: the OK verdict names the HTTP code" \
    || fail "1b: the OK verdict did not name the HTTP code"
[ ! -e "$FLAG" ] \
    && pass "1c: an OK CLEARS a pre-existing stale flag (only proof clears it)" \
    || fail "1c: the stale flag survived a proven-working channel"

# 1d-1f: the credential's ROUTE, proven from what the responder received.
grep -q '"x-rescue-secret"' "$JOURNAL" \
    && pass "1d: the credential is sent as the X-Rescue-Secret HEADER (the header the live intake reads)" \
    || fail "1d: no X-Rescue-Secret header reached the intake"
if python3 - "$JOURNAL" "$FAKE_SECRET" <<'PY'
import json, sys
j, secret = sys.argv[1], sys.argv[2]
for line in open(j, encoding="utf-8"):
    if not line.strip():
        continue
    rec = json.loads(line)
    if secret in rec.get("body", ""):
        sys.exit(1)
sys.exit(0)
PY
then
    pass "1e: the credential is NEVER in the request body"
else
    fail "1e: the credential leaked into the request body"
fi
if grep -q '__AUTHTEST__' "$JOURNAL"; then
    pass "1f: the body is the template's own __AUTHTEST__ self-check (zero ticket residue)"
else
    fail "1f: the body is not the documented __AUTHTEST__ self-check"
fi

# =============================================================================
# (2) RR_SECRET_STALE — 403, and 401
# =============================================================================
echo "--- (2) 401/403 = RR_SECRET_STALE ---"
new_store "$FAKE_SECRET"
rm -f "$FLAG"
start_stub forbidden
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 3 ] \
    && pass "2a: a 403 exits 3 (RR_SECRET_STALE)" \
    || fail "2a: a 403 exited $RC, expected 3"
[ "$(flag_class)" = "RR_SECRET_STALE" ] \
    && pass "2b: a durable RR_SECRET_STALE flag is written" \
    || fail "2b: the flag class is '$(flag_class)', expected RR_SECRET_STALE"
grep -q '"http":403' "$FLAG" \
    && pass "2c: the flag records the HTTP code" \
    || fail "2c: the flag does not record the HTTP code"
grep -q 'operator must re-provision RESCUE_RANGERS_WEBHOOK_SECRET' "$FLAG" \
    && pass "2d: the flag names the remedy and its OWNER (operator-side re-provision)" \
    || fail "2d: the flag does not name the remedy"
if grep -q "$FAKE_SECRET" "$FLAG"; then
    fail "2e: THE CREDENTIAL VALUE IS IN THE FLAG FILE"
else
    pass "2e: the flag records a class and a code, never a value"
fi
if echo "$OUT" | grep -q "$FAKE_SECRET"; then
    fail "2f: the credential value was printed to the operator log"
else
    pass "2f: the credential value is never printed"
fi

rm -f "$FLAG"
start_stub unauth401
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 3 ] && [ "$(flag_class)" = "RR_SECRET_STALE" ] \
    && pass "2g: a 401 is classified the same way as a 403" \
    || fail "2g: a 401 gave rc=$RC class=$(flag_class)"

# =============================================================================
# (3) RR_OLD_RELAY_URL — 200 with missing_message
# =============================================================================
echo "--- (3) 200 missing_message = RR_OLD_RELAY_URL ---"
new_store "$FAKE_SECRET"
rm -f "$FLAG"
start_stub oldrelay
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 4 ] \
    && pass "3a: 200 missing_message exits 4 (RR_OLD_RELAY_URL)" \
    || fail "3a: 200 missing_message exited $RC, expected 4"
[ "$(flag_class)" = "RR_OLD_RELAY_URL" ] \
    && pass "3b: the flag says the URL is wrong, NOT that the secret is stale" \
    || fail "3b: the flag class is '$(flag_class)', expected RR_OLD_RELAY_URL"

# =============================================================================
# (4) UNDETERMINED — a network error is NEVER reported as stale
# =============================================================================
echo "--- (4) network error = UNDETERMINED (never stale) ---"
new_store "$FAKE_SECRET"
rm -f "$FLAG"
# A port nothing is listening on. This is a REAL failed connection attempt, the
# only thing that proves 'unreachable'.
DEAD_PORT="$(python3 -c '
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); print(p)')"
run_check "http://127.0.0.1:$DEAD_PORT/webhook/rr-v2-intake"
[ "$RC" -eq 75 ] \
    && pass "4a: a transport error exits 75 (UNDETERMINED), not 3" \
    || fail "4a: a transport error exited $RC, expected 75"
[ "$(flag_class)" = "UNDETERMINED" ] \
    && pass "4b: the flag says UNDETERMINED" \
    || fail "4b: the flag class is '$(flag_class)', expected UNDETERMINED"
if echo "$OUT" | grep -q "RR_SECRET_STALE"; then
    fail "4c: a network error was reported as a stale credential"
else
    pass "4c: a network error is NEVER reported as a stale credential"
fi

# 4d: a 5xx is the RECEIVER's problem, not this box's credential.
rm -f "$FLAG"
start_stub servererr
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 75 ] && [ "$(flag_class)" = "UNDETERMINED" ] \
    && pass "4d: a 5xx is UNDETERMINED, not stale" \
    || fail "4d: a 5xx gave rc=$RC class=$(flag_class)"

# 4e: an unrecognised 2xx is UNDETERMINED, not a silent OK and not stale.
rm -f "$FLAG"
start_stub garbage
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 75 ] \
    && pass "4e: an unrecognised 2xx body is UNDETERMINED, never a silent OK" \
    || fail "4e: an unrecognised 2xx exited $RC, expected 75"

# =============================================================================
# (5) An UNPROVEN result never erases a PROVEN one
# =============================================================================
echo "--- (5) UNDETERMINED must not overwrite a proven flag ---"
new_store "$FAKE_SECRET"
start_stub forbidden
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$(flag_class)" = "RR_SECRET_STALE" ] \
    && pass "5a: precondition, a proven RR_SECRET_STALE flag is on file" \
    || fail "5a: precondition failed, class=$(flag_class)"
run_check "http://127.0.0.1:$DEAD_PORT/webhook/rr-v2-intake"
[ "$(flag_class)" = "RR_SECRET_STALE" ] \
    && pass "5b: an UNDETERMINED pass LEAVES the proven stale flag in place" \
    || fail "5b: an unproven result overwrote a proven one (class=$(flag_class))"
echo "$OUT" | grep -q "LEFT IN PLACE" \
    && pass "5c: the decision to keep the proven flag is stated, not silent" \
    || fail "5c: the flag was kept silently"

# =============================================================================
# (6) RR_SECRET_MISSING — absence proven, and NOTHING is sent
# =============================================================================
echo "--- (6) no credential anywhere = RR_SECRET_MISSING, no request ---"
new_store ""
rm -f "$FLAG"
start_stub suppressed
run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
[ "$RC" -eq 5 ] \
    && pass "6a: a box with no credential exits 5 (RR_SECRET_MISSING)" \
    || fail "6a: a box with no credential exited $RC, expected 5"
[ "$(flag_class)" = "RR_SECRET_MISSING" ] \
    && pass "6b: the flag distinguishes MISSING from STALE" \
    || fail "6b: the flag class is '$(flag_class)', expected RR_SECRET_MISSING"
echo "$OUT" | grep -q "$BOX/secrets/.env" \
    && pass "6c: the absence NAMES both sources checked (env and the secrets store)" \
    || fail "6c: the absence claim does not name what was checked"
[ ! -s "$JOURNAL" ] \
    && pass "6d: NO request was sent when there is nothing to test" \
    || fail "6d: a request was sent with no credential"

# =============================================================================
# (7) CONTROL ON THE INSTRUMENT — the harness can produce every verdict
# =============================================================================
# Without this, a suite that only ever saw one class could be green because the
# responder is broken rather than because the classifier works.
echo "--- (7) control: the harness reaches every class ---"
new_store "$FAKE_SECRET"
_seen=""
for _m in suppressed forbidden oldrelay; do
  rm -f "$FLAG"
  start_stub "$_m"
  run_check "http://127.0.0.1:$PORT/webhook/rr-v2-intake"
  _seen="$_seen $RC"
done
[ "$_seen" = " 0 3 4" ] \
    && pass "7a: the same harness yields 0 / 3 / 4 for the three server shapes (the classifier discriminates)" \
    || fail "7a: the harness produced '$_seen', expected ' 0 3 4'"

# =============================================================================
# (8) WIRING — the check is reachable and the report surfaces the flag
# =============================================================================
echo "--- (8) wiring ---"
grep -q "rr-intake-auth-check" "$REPO_ROOT/65-rescue-receiver/wire.sh" \
    && pass "8a: wire.sh registers the daily auth-check cron (not dead code)" \
    || fail "8a: wire.sh never registers the auth check"
grep -q "no-deliver" "$REPO_ROOT/65-rescue-receiver/wire.sh" \
    && pass "8b: wire.sh asks for delivery none" \
    || fail "8b: wire.sh does not request --no-deliver"
grep -q "rr-intake-auth.flag" "$REPO_ROOT/65-rescue-receiver/rr-readiness.sh" \
    && pass "8c: rr-readiness.sh's report reads the flag file (the daily surface)" \
    || fail "8c: nothing surfaces the flag in the daily report"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL assertion(s) failed"
  exit 1
fi
echo "PASS: all assertions passed"
exit 0

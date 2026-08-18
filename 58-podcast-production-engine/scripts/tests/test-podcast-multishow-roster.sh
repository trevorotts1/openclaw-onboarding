#!/usr/bin/env bash
# test-podcast-multishow-roster.sh -- T6 verification (two-show model).
#
# Tests the roster-row logic that provision-podcast-client.sh (--show) and
# revoke-podcast-client.sh (--client-email) use against the n8n Data Tables
# API, where podcast_publish_roster holds ONE ROW PER SHOW: same client email
# + last_name, a different podbean_channel_id per show (personal + interview).
#
# The functions under test are extracted from the real scripts (T6-MARKER-BEGIN
# / T6-MARKER-END brackets) and run against a throwaway local mock of the n8n
# data-table endpoints (mock-n8n-datatable-server.py, seeded per scenario), so
# the tests exercise the exact shipped code paths without touching the live
# n8n instance or the real roster.
#
# Usage:
#   bash 58-podcast-production-engine/scripts/tests/test-podcast-multishow-roster.sh
#
# Pass criteria (every check must hold):
#   GUARD: bash -n passes on both changed scripts.
#   PROVISION:
#     P1 two --show values create two roster rows (one per show, same email and
#        last_name, distinct channels, good_standing=YES) and emit exactly the
#        two PODBEAN_PODCAST_ID_<SLUG> env lines on stdout.
#     P2 re-running is idempotent: existing rows are reused, never duplicated.
#     P3 a failing row-create dies fail-closed (no half-provisioned show).
#     P4 a failing roster read dies fail-closed (never guesses the row state).
#     P5 PODCAST_CLIENT_LAST_NAME overrides the derived last name.
#     P6 --dry-run writes nothing and still emits the env lines.
#     P7 with no --show, nothing is written (legacy single-channel flow intact).
#     P8 the API key value never appears anywhere in script output.
#   REVOKE:
#     R1 ALL rows for the client email are flipped to good_standing=NO (loop,
#        not just one row); other clients' rows are untouched.
#     R2 rows already NO are counted as kept, not re-patched.
#     R3 a failing roster read marks the revocation failed (fail-closed).
#     R4 a failing patch marks the revocation failed (the show could publish).
#     R5 no rows for the email is a clean no-op.
#     R6 --dry-run flips nothing.
#     R7 revoke derives the email from the provision ledger's roster_email fact
#        (closed loop: provision writes it, revoke reads it back).
#   MUTATION PROOF (verified during development):
#     - forcing revoke to process only the FIRST row (head -n1, the original
#       single-row defect) makes R1 FAIL (RED); reverting restores GREEN.
#     - skipping provision's read-before-create makes P2 FAIL with duplicates
#       (RED); reverting restores GREEN.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PROV="$REPO_ROOT/58-podcast-production-engine/scripts/provision-podcast-client.sh"
REV="$REPO_ROOT/58-podcast-production-engine/scripts/revoke-podcast-client.sh"
MOCK="$REPO_ROOT/58-podcast-production-engine/scripts/tests/mock-n8n-datatable-server.py"

PASS_COUNT=0
pass() { PASS_COUNT=$((PASS_COUNT+1)); echo "[PASS] $*"; }
fail() { echo "[FAIL] $*" >&2; exit 1; }

# --------------------------------------------------------------------------- #
# GUARD: bash -n both changed scripts
# --------------------------------------------------------------------------- #
bash -n "$PROV" || fail "bash -n provision-podcast-client.sh failed"
bash -n "$REV"  || fail "bash -n revoke-podcast-client.sh failed"
pass "bash -n passes on both scripts"

# --------------------------------------------------------------------------- #
# Workspace: extract the functions under test, start the mock server
# --------------------------------------------------------------------------- #
WORK="$(mktemp -d /tmp/podcast-t6-test.XXXXXX)"
MOCK_PID=""
cleanup() {
  [ -n "$MOCK_PID" ] && kill "$MOCK_PID" 2>/dev/null || true
  rm -rf "$WORK"
}
trap cleanup EXIT

LIB_PROV="$WORK/lib-provision.sh"
LIB_REV="$WORK/lib-revoke.sh"
sed -n '/^# T6-MARKER-BEGIN provision_roster_rows/,/^# T6-MARKER-END provision_roster_rows/p' "$PROV" > "$LIB_PROV"
sed -n '/^# T6-MARKER-BEGIN revoke_roster_rows/,/^# T6-MARKER-END revoke_roster_rows/p' "$REV" > "$LIB_REV"
grep -q '^provision_roster_rows()' "$LIB_PROV" || fail "could not extract provision_roster_rows"
grep -q '^revoke_roster_rows()' "$LIB_REV" || fail "could not extract revoke_roster_rows"
pass "extraction markers present in both scripts"

TABLE="T6TESTTABLE0001"
API_KEY="dummy-key-value-t6"
PORT=""
STATE="$WORK/state.json"
SEED="$WORK/seed.json"

start_mock() {  # start_mock <seed-json-file>
  PORT=$(( (RANDOM % 20000) + 30000 ))
  rm -rf "$WORK/control"
  mkdir -p "$WORK/control"
  rm -f "$STATE" "$WORK/steps.log" "$WORK/facts.log"
  cp "$1" "$SEED"
  python3 "$MOCK" "$WORK" "$TABLE" "$PORT" > "$WORK/server.log" 2>&1 &
  MOCK_PID=$!
  local i
  for i in $(seq 1 50); do
    curl -s -o /dev/null "http://127.0.0.1:$PORT/api/v1/data-tables/$TABLE/rows" && return 0
    sleep 0.1
  done
  fail "mock n8n server did not come up (log: $WORK/server.log)"
}
stop_mock() { [ -n "$MOCK_PID" ] && kill "$MOCK_PID" 2>/dev/null || true; MOCK_PID=""; }

# run_provision <dry-run 0|1> <client-email> <override-last-name|-> <SLUG:CH>...
run_provision() {
  local dry="$1" email="$2" last="$3"; shift 3
  {
    printf 'set -uo pipefail\n'
    printf 'SHOW_SLUGS=(); SHOW_CHANNELS=()\n'
    local pair
    for pair in "$@"; do
      printf 'SHOW_SLUGS+=("%s"); SHOW_CHANNELS+=("%s")\n' "${pair%%:*}" "${pair#*:}"
    done
    printf 'ALL_EMAILS=("%s")\n' "$email"
    printf 'DRY_RUN="%s" SLUG="t6-test" LEDGER_DIR="%s"\n' "$dry" "$WORK"
    printf 'N8N_API_URL="http://127.0.0.1:%s/" N8N_API_KEY="%s" ROSTER_TABLE_ID="%s"\n' "$PORT" "$API_KEY" "$TABLE"
    [ "$last" != "-" ] && printf 'PODCAST_CLIENT_LAST_NAME="%s"\n' "$last"
    printf 'STEPS="%s" FACTS="%s" T6_SHOW_TAG="t6-test"\n' "$WORK/steps.log" "$WORK/facts.log"
    printf 'log()  { printf "%%s\\n" "$*" >&2; }\n'
    printf 'die()  { local code="$1"; shift; echo "DIE $code: $*"; exit "$code"; }\n'
    printf 'ledger_step() { local n="$1" s="$2" d="${3:-}"; echo "[$s] $n${d:+ - $d}" >> "$STEPS"; }\n'
    printf 'ledger_fact() { echo "$1=$2" >> "$FACTS"; }\n'
    printf 'n8n_base() { printf "%%s" "${N8N_API_URL%%/}"; }\n'
    printf 'n8n_filter_json() { jq -cn --arg c "$1" --arg v "$2" '"'"'{type:"and",filters:[{columnName:$c,condition:"eq",value:$v}]}'"'"'; }\n'
    printf 'n8n_urlencode() { python3 -c '"'"'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))'"'"' "$1"; }\n'
    printf 'source "%s"\n' "$LIB_PROV"
    printf 'provision_roster_rows\n'
  } > "$WORK/harness.sh"
  bash "$WORK/harness.sh"
}

# run_revoke <dry-run 0|1> <client-email|-> [pledger-file]
run_revoke() {
  local dry="$1" email="$2" pledger="${3:-}"
  {
    printf 'set -uo pipefail\n'
    printf 'CLIENT_EMAIL="%s" PLEDGER="%s" VERIFY_FAIL="0"\n' \
      "$([ "$email" = "-" ] && echo "" || echo "$email")" "$pledger"
    printf 'DRY_RUN="%s" LEDGER_DIR="%s"\n' "$dry" "$WORK"
    printf 'N8N_API_URL="http://127.0.0.1:%s/" N8N_API_KEY="%s" ROSTER_TABLE_ID="%s"\n' "$PORT" "$API_KEY" "$TABLE"
    printf 'STEPS="%s" FACTS="%s"\n' "$WORK/steps.log" "$WORK/facts.log"
    printf 'log()  { printf "%%s\\n" "$*" >&2; }\n'
    printf 'die()  { local code="$1"; shift; echo "DIE $code: $*"; exit "$code"; }\n'
    printf 'ledger_step() { local n="$1" s="$2" d="${3:-}"; echo "[$s] $n${d:+ - $d}" >> "$STEPS"; }\n'
    printf 'ledger_fact() { echo "$1=$2" >> "$FACTS"; }\n'
    printf 'n8n_base() { printf "%%s" "${N8N_API_URL%%/}"; }\n'
    printf 'n8n_filter_json() { jq -cn --arg c "$1" --arg v "$2" '"'"'{type:"and",filters:[{columnName:$c,condition:"eq",value:$v}]}'"'"'; }\n'
    printf 'n8n_urlencode() { python3 -c '"'"'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))'"'"' "$1"; }\n'
    printf 'source "%s"\n' "$LIB_REV"
    printf 'revoke_roster_rows; echo "VERIFY_FAIL=$VERIFY_FAIL" >> "$STEPS"\n'
  } > "$WORK/harness.sh"
  bash "$WORK/harness.sh"
}

state_field() { jq -r "$2" "$STATE" 2>/dev/null | sort; }

# --------------------------------------------------------------------------- #
# PROVISION
# --------------------------------------------------------------------------- #

# --- P1: two shows -> two rows + two env lines ------------------------------
printf '[]' > "$WORK/empty.json"
start_mock "$WORK/empty.json"
OUT="$(run_provision 0 "Sample@Example.com" "-" "PERSONAL:channelA1" "INTERVIEW:channelB2")" || fail "P1: provision exited nonzero"
[ "$OUT" = "$(printf 'PODBEAN_PODCAST_ID_PERSONAL=channelA1\nPODBEAN_PODCAST_ID_INTERVIEW=channelB2')" ] \
  || fail "P1: stdout env lines wrong: [$OUT]"
pass "P1: stdout carries exactly the two PODBEAN_PODCAST_ID_<SLUG> env lines"
[ "$(jq 'length' "$STATE")" = "2" ] || fail "P1: expected 2 roster rows, got $(jq 'length' "$STATE")"
[ "$(state_field x '.[].email' | uniq)" = "sample@example.com" ] || fail "P1: email not lowercased per row"
[ "$(state_field x '.[].last_name' | uniq)" = "sample" ] || fail "P1: last_name not derived from email pre-@"
[ "$(jq -r '[.[] | select(.podbean_channel_id=="channelA1")] | .[0].good_standing' "$STATE")" = "YES" ] || fail "P1: good_standing not YES"
[ "$(jq -r '[.[] | select(.podbean_channel_id=="channelB2")] | .[0].good_standing' "$STATE")" = "YES" ] || fail "P1: second row good_standing not YES"
pass "P1: two roster rows created (same email/last_name, distinct channels, good_standing=YES)"
grep -q '\[OK\] roster:PERSONAL' "$WORK/steps.log" || fail "P1: no OK step for PERSONAL"
grep -q '\[OK\] roster:INTERVIEW' "$WORK/steps.log" || fail "P1: no OK step for INTERVIEW"
pass "P1: ledger steps recorded for both shows"
grep -q '^roster_email=sample@example.com$' "$WORK/facts.log" || fail "P1: roster_email fact not persisted (revoke derives it from here)"
grep -q '^roster_last_name=sample$' "$WORK/facts.log" || fail "P1: roster_last_name fact not persisted"
pass "P1: roster_email/last_name facts persisted for revoke to derive"

# --- P2: idempotent re-run -> reuse, never duplicate ------------------------
OUT2="$(run_provision 0 "Sample@Example.com" "-" "PERSONAL:channelA1" "INTERVIEW:channelB2")" || fail "P2: re-run exited nonzero"
[ "$(jq 'length' "$STATE")" = "2" ] || fail "P2: duplicate rows inserted ($(jq 'length' "$STATE"))"
grep -q '\[REUSE\] roster:PERSONAL' "$WORK/steps.log" || fail "P2: PERSONAL not reused"
grep -q '\[REUSE\] roster:INTERVIEW' "$WORK/steps.log" || fail "P2: INTERVIEW not reused"
[ "$OUT2" = "$OUT" ] || fail "P2: env lines differ on re-run"
pass "P2: re-run reuses existing rows, inserts no duplicates, same env lines"

# --- P5: PODCAST_CLIENT_LAST_NAME override ----------------------------------
run_provision 0 "sample@example.com" "Placeholder" "SOLO:channelC3" >/dev/null || fail "P5: provision exited nonzero"
[ "$(jq -r '[.[] | select(.podbean_channel_id=="channelC3")] | .[0].last_name' "$STATE")" = "Placeholder" ] \
  || fail "P5: override last_name not stored"
pass "P5: PODCAST_CLIENT_LAST_NAME overrides the derived last name"

# --- P8: secret hygiene (API key value never in output) ---------------------
ALL_OUT="$(run_provision 0 "sample@example.com" "-" "AUDIT:channelD4" 2>&1)" || true
printf '%s' "$ALL_OUT" | grep -q "$API_KEY" && fail "P8: API key value leaked in output"
pass "P8: the N8N API key value never appears in script output"

# --- P6: dry-run writes nothing, still emits env lines -----------------------
stop_mock; start_mock "$WORK/empty.json"
OUT6="$(run_provision 1 "sample@example.com" "-" "PERSONAL:channelA1")" || fail "P6: dry-run exited nonzero"
[ "$OUT6" = "PODBEAN_PODCAST_ID_PERSONAL=channelA1" ] || fail "P6: dry-run must still print the env line"
[ "$(jq 'length' "$STATE")" = "0" ] || fail "P6: dry-run wrote a row"
grep -q '\[DRY-RUN\] roster:PERSONAL' "$WORK/steps.log" || fail "P6: no DRY-RUN step logged"
pass "P6: dry-run emits the env line, logs DRY-RUN, writes no row"

# --- P7: legacy flow (no --show) -> nothing written --------------------------
OUT7="$(run_provision 0 "sample@example.com" "-")" || fail "P7: no-show run exited nonzero"
[ -z "$OUT7" ] || fail "P7: no-show run must print nothing, got [$OUT7]"
[ "$(jq 'length' "$STATE")" = "0" ] || fail "P7: no-show run wrote a row"
pass "P7: with no --show, no roster write and no output (legacy flow unchanged)"

# --- P3: failing create -> die 18 fail-closed --------------------------------
stop_mock; start_mock "$WORK/empty.json"
touch "$WORK/control/fail_post"
RC=0; OUT3="$(run_provision 0 "sample@example.com" "-" "PERSONAL:channelA1" 2>&1)" || RC=$?
[ "$RC" = "18" ] || fail "P3: expected exit 18 on create failure, got $RC"
[ "$(jq 'length' "$STATE")" = "0" ] || fail "P3: row persisted despite create failure"
printf '%s' "$OUT3" | grep -q "DIE 18" || fail "P3: no hard-stop message"
pass "P3: failing row-create dies fail-closed (exit 18), nothing persisted"

# --- P4: failing read -> die 17 fail-closed ----------------------------------
rm -f "$WORK/control/fail_post"; touch "$WORK/control/fail_read"
RC=0; OUT4="$(run_provision 0 "sample@example.com" "-" "PERSONAL:channelA1" 2>&1)" || RC=$?
[ "$RC" = "17" ] || fail "P4: expected exit 17 on read failure, got $RC"
printf '%s' "$OUT4" | grep -q "DIE 17" || fail "P4: no hard-stop message"
pass "P4: failing roster read dies fail-closed (exit 17), never guesses"

# --------------------------------------------------------------------------- #
# REVOKE
# --------------------------------------------------------------------------- #

# --- R1: ALL rows for the client flipped; other clients untouched ------------
cat > "$WORK/seed2.json" <<'SEED'
[
 {"id": 101, "email": "client@example.com", "last_name": "Placeholder", "podbean_channel_id": "channelA1", "good_standing": "YES", "first_name": "", "notes": ""},
 {"id": 102, "email": "client@example.com", "last_name": "Placeholder", "podbean_channel_id": "channelB2", "good_standing": "YES", "first_name": "", "notes": ""},
 {"id": 103, "email": "other@example.com",  "last_name": "Other",  "podbean_channel_id": "channelZ9", "good_standing": "YES", "first_name": "", "notes": ""}
]
SEED
stop_mock; start_mock "$WORK/seed2.json"
run_revoke 0 "client@example.com" || fail "R1: revoke exited nonzero"
[ "$(jq -r '[.[] | select(.email=="client@example.com" and .good_standing=="NO")] | length' "$STATE")" = "2" ] \
  || fail "R1: not ALL client rows flipped to NO"
[ "$(jq -r '[.[] | select(.email=="other@example.com")] | .[0].good_standing' "$STATE")" = "YES" ] \
  || fail "R1: another client's row was touched"
grep -q 'VERIFY_FAIL=0' "$WORK/steps.log" || fail "R1: VERIFY_FAIL not 0"
grep -q 'revoked, 0 already NO (all shows cut)' "$WORK/steps.log" || fail "R1: summary step missing"
pass "R1: ALL roster rows for the email flipped to NO; other clients untouched"

# --- R2: rows already NO counted as kept --------------------------------------
jq '(.[] | select(.id==101)).good_standing = "NO"' "$WORK/seed2.json" > "$WORK/seed3.json"
stop_mock; start_mock "$WORK/seed3.json"
run_revoke 0 "client@example.com" || fail "R2: revoke exited nonzero"
grep -q '\[OK\] 10-roster-revoke:row101 - already good_standing=NO' "$WORK/steps.log" || fail "R2: pre-NO row not counted as kept"
grep -q '1 revoked, 1 already NO' "$WORK/steps.log" || fail "R2: summary counts wrong"
pass "R2: rows already NO are kept, not re-patched"

# --- R5: no rows for the email -> clean no-op ---------------------------------
stop_mock; start_mock "$WORK/seed2.json"
run_revoke 0 "nobody@example.com" || fail "R5: revoke exited nonzero"
grep -q 'no roster rows for nobody@example.com (nothing to revoke)' "$WORK/steps.log" || fail "R5: no-op step missing"
grep -q 'VERIFY_FAIL=0' "$WORK/steps.log" || fail "R5: VERIFY_FAIL not 0"
pass "R5: unknown email is a clean no-op (fail-closed gates still refuse)"

# --- R6: dry-run flips nothing -------------------------------------------------
stop_mock; start_mock "$WORK/seed2.json"
run_revoke 1 "client@example.com" || fail "R6: dry-run exited nonzero"
[ "$(jq -r '[.[] | select(.good_standing=="NO")] | length' "$STATE")" = "0" ] || fail "R6: dry-run flipped rows"
grep -q '\[DRY-RUN\] 10-roster-revoke' "$WORK/steps.log" || fail "R6: no DRY-RUN step"
pass "R6: dry-run flips nothing"

# --- R7: revoke derives the email from the provision ledger (no --client-email) -
# Revoke reads .facts.roster_email, which provision-podcast-client.sh writes via
# ledger_fact "roster_email" in STEP 5b. Fabricate that ledger here.
PLEDGER_FILE="$WORK/provision-ledger.json"
printf '{"slug":"t6","facts":{"roster_email":"client@example.com"}}' > "$PLEDGER_FILE"
stop_mock; start_mock "$WORK/seed2.json"
run_revoke 0 "-" "$PLEDGER_FILE" || fail "R7: revoke exited nonzero"
[ "$(jq -r '[.[] | select(.email=="client@example.com" and .good_standing=="NO")] | length' "$STATE")" = "2" ] \
  || fail "R7: email not derived from provision ledger"
pass "R7: revoke derives the roster email from the provision ledger (no --client-email)"

# --- R3: failing read -> FAIL + VERIFY_FAIL=1 ----------------------------------
stop_mock; start_mock "$WORK/seed2.json"
touch "$WORK/control/fail_read"
run_revoke 0 "client@example.com" || fail "R3: revoke exited nonzero"
grep -q '\[FAIL\] 10-roster-revoke' "$WORK/steps.log" || fail "R3: no FAIL step"
grep -q 'VERIFY_FAIL=1' "$WORK/steps.log" || fail "R3: VERIFY_FAIL not 1"
pass "R3: failing roster read marks the revocation FAILED (fail-closed)"

# --- R4: failing patch -> FAIL + VERIFY_FAIL=1 ----------------------------------
rm -f "$WORK/control/fail_read"; stop_mock; start_mock "$WORK/seed2.json"
touch "$WORK/control/fail_patch"
run_revoke 0 "client@example.com" || fail "R4: revoke exited nonzero"
grep -q '\[FAIL\] 10-roster-revoke:row10' "$WORK/steps.log" || fail "R4: no per-row FAIL step"
grep -q 'VERIFY_FAIL=1' "$WORK/steps.log" || fail "R4: VERIFY_FAIL not 1"
pass "R4: failing patch marks the revocation FAILED (a show could still publish)"

echo ""
echo "ALL $PASS_COUNT CHECKS PASSED (T6 multishow roster: provision + revoke)"

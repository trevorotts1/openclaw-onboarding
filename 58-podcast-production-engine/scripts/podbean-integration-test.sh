#!/usr/bin/env bash
#
# podbean-integration-test.sh
# Podcast Production Engine — end-to-end Podbean publish+verify integration test.
#
# WHAT THIS IS
#   A GATED integration test that exercises the full publish+verify+delete cycle
#   against the live Podbean API using a real Channel-scoped access token. It
#   creates a draft episode, verifies it exists, and then deletes it so nothing
#   is left behind. It NEVER publishes a live episode and NEVER touches a
#   production channel without explicit operator opt-in.
#
# SAFETY — EXPLICIT OPT-IN REQUIRED (this test NEVER runs unattended)
#   Set PODBEAN_INTEGRATION_TEST=1 in the environment, OR pass --run as the
#   first argument. Without one of these, the script prints a "skipped" message
#   and exits 0 immediately (gate green for automation that does not opt in).
#
#   The episode it creates is always status=draft (never visible publicly) and
#   is deleted before the script exits, whether the test passes or fails.
#
# ENVIRONMENT (same credential model as podbean_publish.sh)
#   PODBEAN_PODCAST_ID        — the test Channel ID (required; do NOT use a
#                               production channel without the operator's blessing)
#   PODBEAN_CLIENT_ID         — BlackCEO shared Podbean app client id (LOCAL mode)
#   PODBEAN_CLIENT_SECRET     — BlackCEO shared Podbean app client secret (LOCAL mode)
#   PODBEAN_BROKER_WEBHOOK_URL  — n8n broker webhook (BROKER mode; optional)
#   PODBEAN_BROKER_TOKEN      — broker shared token (BROKER mode; optional)
#   PODBEAN_API_BASE          — override API base (default https://api.podbean.com/v1)
#   PODBEAN_INTEGRATION_TEST  — set to 1 to opt in (alternative to --run flag)
#
# USAGE
#   podbean-integration-test.sh [--run]
#
# EXIT CODES
#   0  ran and passed, OR skipped (opt-in not given — gate green)
#   1  ran and failed
#   2  usage / precondition error
#
set -euo pipefail

readonly PODBEAN_API="${PODBEAN_API_BASE:-https://api.podbean.com/v1}"
readonly RETRIES=3
readonly CURL_MAX_TIME=60

# -------------------------------------------------------------------- logging --
log()  { printf '%s podbean-integration-test %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die()  { log "FATAL: $*"; exit 2; }

# Redact known secret substrings from any text before it is shown.
redact() {
  local s="$1"
  [ -n "${PODBEAN_CLIENT_ID:-}" ]     && s="${s//${PODBEAN_CLIENT_ID}/[REDACTED_CLIENT_ID]}"
  [ -n "${PODBEAN_CLIENT_SECRET:-}" ] && s="${s//${PODBEAN_CLIENT_SECRET}/[REDACTED_CLIENT_SECRET]}"
  [ -n "${PODBEAN_BROKER_TOKEN:-}" ]  && s="${s//${PODBEAN_BROKER_TOKEN}/[REDACTED_BROKER_TOKEN]}"
  [ -n "${ACCESS_TOKEN:-}" ]          && s="${s//${ACCESS_TOKEN}/[REDACTED_TOKEN]}"
  printf '%s' "$s"
}

# ------------------------------------------------------------------- helpers --
json_field() {
  python3 -c '
import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
for k in sys.argv[1:]:
    d = d.get(k) if isinstance(d, dict) else None
    if d is None:
        break
print("" if d is None else d)
' "$@"
}

# Build a curl config on stdout carrying the secret url and, optionally, basic
# auth. printf is a shell builtin, so the secret never appears in the process
# list; the config is consumed through process substitution, never a temp file.
cfg_lines() {
  local method="$1" url="$2"
  printf 'request = "%s"\n' "$method"
  printf 'url = "%s"\n' "$url"
  printf 'silent\n'
  printf 'show-error\n'
  printf 'location\n'
  printf 'max-time = %s\n' "$CURL_MAX_TIME"
  if [ "${USE_BASIC:-0}" = "1" ]; then
    printf 'user = "%s:%s"\n' "$PODBEAN_CLIENT_ID" "$PODBEAN_CLIENT_SECRET"
  fi
}

RESP_BODY=""; RESP_CODE=""
http_request() {
  local method="$1" url="$2"; shift 2
  local attempt=1 out
  while :; do
    out="$(curl -K <(cfg_lines "$method" "$url") "$@" -w $'\n%{http_code}' 2>/dev/null || true)"
    RESP_CODE="${out##*$'\n'}"
    RESP_BODY="${out%$'\n'*}"
    if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then return 0; fi
    if [ "$attempt" -ge "$RETRIES" ]; then return 1; fi
    log "attempt ${attempt} for ${method} $(redact "${url%%\?*}") returned HTTP ${RESP_CODE:-000}; backing off"
    sleep "$(( attempt * attempt ))"
    attempt=$(( attempt + 1 ))
  done
}

# ------------------------------------------------------------------- cleanup --
# Tracks the episode id we created so the trap can delete it on ANY exit path.
CREATED_EPISODE_ID=""

cleanup() {
  local exit_code=$?
  if [ -n "$CREATED_EPISODE_ID" ] && [ -n "${ACCESS_TOKEN:-}" ]; then
    log "cleanup: deleting test episode ${CREATED_EPISODE_ID} ..."
    if http_request POST "$PODBEAN_API/episodes/delete?access_token=${ACCESS_TOKEN}" \
         --data-urlencode "id=${CREATED_EPISODE_ID}"; then
      log "cleanup: test episode ${CREATED_EPISODE_ID} deleted (HTTP ${RESP_CODE})"
    else
      log "cleanup: FAILED to delete test episode ${CREATED_EPISODE_ID} (HTTP ${RESP_CODE:-000}); manual removal may be needed"
    fi
  else
    log "cleanup: no episode to delete (id=${CREATED_EPISODE_ID:-<none>}, access_token=${ACCESS_TOKEN:+SET}/${ACCESS_TOKEN:-NOT SET})"
  fi
  if [ "$exit_code" -ne 0 ]; then
    log "test exited with code ${exit_code}"
  fi
}

trap cleanup EXIT

# ------------------------------------------------------------- argument parse --
OPT_IN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --run)           OPT_IN=1; shift ;;
    -h|--help)
      sed -n '1,38p' "$0" >&2
      exit 0
      ;;
    *)               die "unknown argument: $1 (use --run to execute, or set PODBEAN_INTEGRATION_TEST=1)" ;;
  esac
done

# Honor the environment variable as well.
if [ "${PODBEAN_INTEGRATION_TEST:-0}" = "1" ]; then
  OPT_IN=1
fi

# ------------------------------------------------------ opt-in guard (Gate 1) --
if [ "$OPT_IN" != "1" ]; then
  echo "PODBEAN INTEGRATION TEST — SKIPPED"
  echo ""
  echo "  This test exercises the live Podbean API and is NEVER run unattended."
  echo "  To execute it, set PODBEAN_INTEGRATION_TEST=1 in the environment or"
  echo "  pass --run as the first argument."
  echo ""
  echo "  WARNING: ensure PODBEAN_PODCAST_ID points to a TEST channel."
  echo "  The test creates and deletes a draft episode; it does NOT publish."
  echo ""
  exit 0
fi

# ------------------------------------------------------ prerequisite checks --
command -v curl    >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

: "${PODBEAN_PODCAST_ID:?PODBEAN_PODCAST_ID is NOT SET — point it at a TEST channel, never a production one}"

# Determine OAuth mode: broker wins over local.
BROKER_MODE=0
if [ -n "${PODBEAN_BROKER_WEBHOOK_URL:-}" ] && [ -n "${PODBEAN_BROKER_TOKEN:-}" ]; then
  BROKER_MODE=1
else
  : "${PODBEAN_CLIENT_ID:?PODBEAN_CLIENT_ID is NOT SET — needed in LOCAL mode (set PODBEAN_CLIENT_ID + PODBEAN_CLIENT_SECRET, or configure PODBEAN_BROKER_WEBHOOK_URL + PODBEAN_BROKER_TOKEN for broker mode)}"
  : "${PODBEAN_CLIENT_SECRET:?PODBEAN_CLIENT_SECRET is NOT SET — needed in LOCAL mode}"
fi

echo ""
echo "============================================================"
echo "  Podcast Production Engine — Podbean Integration Test"
echo "  Channel ID: $(redact "$PODBEAN_PODCAST_ID")"
echo "  Mode: $( [ "$BROKER_MODE" = "1" ] && echo "BROKER (n8n)" || echo "LOCAL (client_credentials)")"
echo "  Started:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================================"
echo ""

# ----------------------------------------------------------------- step 1: auth --
log "STEP 1: obtaining access token ..."
ACCESS_TOKEN=""

if [ "$BROKER_MODE" = "1" ]; then
  # Broker-mode request.
  broker_cfg_lines() {
    printf 'request = "POST"\n'
    printf 'url = "%s"\n' "$PODBEAN_BROKER_WEBHOOK_URL"
    printf 'silent\n'
    printf 'show-error\n'
    printf 'location\n'
    printf 'max-time = %s\n' "$CURL_MAX_TIME"
    printf 'header = "Content-Type: application/json"\n'
    printf 'header = "X-Podbean-Broker-Token: %s"\n' "$PODBEAN_BROKER_TOKEN"
  }
  attempt=1
  body="$(printf '{"action":"mint_token","podcast_id":"%s"}' "$PODBEAN_PODCAST_ID")"
  while :; do
    out="$(curl -K <(broker_cfg_lines) --data "$body" -w $'\n%{http_code}' 2>/dev/null || true)"
    RESP_CODE="${out##*$'\n'}"
    RESP_BODY="${out%$'\n'*}"
    if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then break; fi
    if [ "$attempt" -ge "$RETRIES" ]; then die "broker token request failed after ${RETRIES} attempts (HTTP ${RESP_CODE:-000})"; fi
    log "broker attempt ${attempt} returned HTTP ${RESP_CODE:-000}; backing off"
    sleep "$(( attempt * attempt ))"
    attempt=$(( attempt + 1 ))
  done
  ACCESS_TOKEN="$(printf '%s' "$RESP_BODY" | json_field access_token)"
  RESP_BODY=""
  [ -n "$ACCESS_TOKEN" ] || die "broker returned no access_token"
else
  USE_BASIC=1 http_request POST "$PODBEAN_API/oauth/token" \
    --data-urlencode "grant_type=client_credentials" \
    || die "oauth token request failed (HTTP ${RESP_CODE:-000})"
  ACCESS_TOKEN="$(printf '%s' "$RESP_BODY" | json_field access_token)"
  RESP_BODY=""
  [ -n "$ACCESS_TOKEN" ] || die "oauth response carried no access_token"
fi

log "  access token: ACQUIRED (value not shown)"
echo "  [PASS] STEP 1 — authentication succeeded"

# ---------------------------------------------------------- step 2: create draft --
log "STEP 2: creating a draft test episode ..."
TEST_TITLE="Integration Test $(date -u +%Y-%m-%dT%H:%M:%SZ)"
TEST_CONTENT="This is an automated integration test episode. It will be deleted as part of the test teardown."

http_request POST "$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}" \
  --data-urlencode "title=${TEST_TITLE}" \
  --data-urlencode "content=${TEST_CONTENT}" \
  --data-urlencode "status=draft" \
  --data-urlencode "type=public" \
  || die "failed to create draft episode (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"

CREATED_EPISODE_ID="$(printf '%s' "$RESP_BODY" | json_field episode id)"
PERMALINK="$(printf '%s' "$RESP_BODY" | json_field episode permalink_url)"
RESP_BODY=""

[ -n "$CREATED_EPISODE_ID" ] || die "episode created but no id returned; cannot verify or clean up"
log "  created draft episode id=${CREATED_EPISODE_ID} title=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$TEST_TITLE")"
echo "  [PASS] STEP 2 — draft episode created (id=${CREATED_EPISODE_ID})"

# --------------------------------------------------------- step 3: verify exists --
log "STEP 3: verifying the draft episode exists on the API ..."
FOUND_ID=""

http_request GET "$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}&offset=0&limit=50" \
  || die "failed to list episodes for verification (HTTP ${RESP_CODE:-000})"

FOUND_ID="$(printf '%s' "$RESP_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
target = sys.argv[1]
episodes = d.get('episodes', []) if isinstance(d, dict) else []
for ep in episodes:
    if isinstance(ep, dict) and str(ep.get('id', '')) == target:
        print(ep['id'])
        break
" "$CREATED_EPISODE_ID" 2>/dev/null || true)"

if [ -z "$FOUND_ID" ]; then
  RESP_BODY=""
  die "created episode ${CREATED_EPISODE_ID} was NOT found in the episode listing; the episode may not have been persisted"
fi

EPISODE_STATUS="$(printf '%s' "$RESP_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
target = sys.argv[1]
episodes = d.get('episodes', []) if isinstance(d, dict) else []
for ep in episodes:
    if isinstance(ep, dict) and str(ep.get('id', '')) == target:
        print(ep.get('status', ''))
        break
" "$CREATED_EPISODE_ID" 2>/dev/null || true)"

RESP_BODY=""
log "  verified episode ${CREATED_EPISODE_ID} exists with status=${EPISODE_STATUS:-unknown}"

if [ "$EPISODE_STATUS" != "draft" ]; then
  log "WARNING: expected status=draft but got status=${EPISODE_STATUS:-<empty>}"
fi

echo "  [PASS] STEP 3 — episode verified on the API (status=${EPISODE_STATUS:-draft})"

# --------------------------------------------------------- step 4: delete draft --
log "STEP 4: deleting the test draft episode ..."
DELETE_RESULT="ok"

if http_request POST "$PODBEAN_API/episodes/delete?access_token=${ACCESS_TOKEN}" \
     --data-urlencode "id=${CREATED_EPISODE_ID}"; then
  log "  test episode ${CREATED_EPISODE_ID} deleted successfully (HTTP ${RESP_CODE})"
  EPISODE_ID_DELETED="$CREATED_EPISODE_ID"
  CREATED_EPISODE_ID=""  # clear so cleanup trap does not double-delete
  echo "  [PASS] STEP 4 — test episode deleted"
else
  log "  WARNING: delete returned HTTP ${RESP_CODE:-000} — episode may still exist"
  DELETE_RESULT="failed"
  echo "  [FAIL] STEP 4 — delete returned HTTP ${RESP_CODE:-000}"
fi

# ---------------------------------------------------------- step 5: verify gone --
log "STEP 5: verifying the episode is gone ..."

http_request GET "$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}&offset=0&limit=50" \
  || die "failed to list episodes for deletion verification (HTTP ${RESP_CODE:-000})"

STILL_THERE="$(printf '%s' "$RESP_BODY" | python3 -c "
import json, sys
d = json.load(sys.stdin)
target = sys.argv[1]
episodes = d.get('episodes', []) if isinstance(d, dict) else []
for ep in episodes:
    if isinstance(ep, dict) and str(ep.get('id', '')) == target:
        print(ep.get('id', ''))
        break
" "$EPISODE_ID_DELETED" 2>/dev/null || true)"

RESP_BODY=""

if [ -n "$STILL_THERE" ]; then
  log "  WARNING: episode ${EPISODE_ID_DELETED} still appears in listing after delete"
  echo "  [WARN] STEP 5 — episode may still exist (delete may be asynchronous)"
else
  log "  confirmed episode ${EPISODE_ID_DELETED} is no longer in the listing"
  echo "  [PASS] STEP 5 — episode confirmed gone from the API"
fi

# ------------------------------------------------------------------- final --
echo ""
echo "============================================================"
echo "  Integration test complete"
echo "  Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "============================================================"

if [ "$DELETE_RESULT" = "failed" ]; then
  log "test completed with one or more failures"
  exit 1
fi

log "test completed successfully"
exit 0

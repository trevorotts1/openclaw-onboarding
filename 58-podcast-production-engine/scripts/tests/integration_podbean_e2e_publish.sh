#!/usr/bin/env bash
# =============================================================================
# U040 :: Podbean end-to-end publish+verify integration test
#
# REQUIREMENTS (AC2): explicit opt-in via PODBEAN_E2E_TEST=1. Without that
# environment variable set (or set to anything other than "1"), this test exits
# immediately with status 0 and prints "SKIPPED". It NEVER runs unattended.
# When opted in, the test:
#   1. Obtains a Podbean OAuth access token (client_credentials)
#   2. Creates a tiny dummy audio file and uploads it to Podbean
#   3. Creates a DRAFT episode on the target podcast
#   4. Lists episodes to verify the draft exists
#   5. DELETES the test episode (cleanup)
#   6. Cleans up even on failure (trap EXIT)
#
# CREDENTIAL HABIT: credential values are NEVER printed. The OAuth token,
# client id, and client secret are referenced by label only; access tokens
# are passed to curl via process substitution (printf builtin), never in argv
# (no ps exposure) and never on disk.
#
# RUN:
#   PODBEAN_E2E_TEST=1 bash integration_podbean_e2e_publish.sh
#
# Required environment when opted in:
#   PODBEAN_CLIENT_ID        BlackCEO shared Podbean app client id
#   PODBEAN_CLIENT_SECRET    BlackCEO shared Podbean app client secret
#   PODBEAN_PODCAST_ID       target podcast Channel ID for the test
# =============================================================================
set -euo pipefail

readonly PODBEAN_API="${PODBEAN_API_BASE:-https://api.podbean.com/v1}"
readonly CURL_MAX_TIME=30
readonly TEST_TITLE="E2E-TEST-DRAFT-$(date -u +%Y%m%dT%H%M%SZ)"
readonly TEST_CONTENT="Automated end-to-end test draft episode. Safe to delete."

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ------------------------------------------------------------------- logging --
log()  { printf '%s podbean_e2e_test %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die()  { log "ERROR: $*"; exit 1; }

# Redact known secret substrings from any text before it is shown.
redact() {
  local s="$1"
  [ -n "${PODBEAN_CLIENT_ID:-}" ]     && s="${s//${PODBEAN_CLIENT_ID}/[REDACTED_CLIENT_ID]}"
  [ -n "${PODBEAN_CLIENT_SECRET:-}" ] && s="${s//${PODBEAN_CLIENT_SECRET}/[REDACTED_CLIENT_SECRET]}"
  [ -n "${ACCESS_TOKEN:-}" ]          && s="${s//${ACCESS_TOKEN}/[REDACTED_TOKEN]}"
  printf '%s' "$s"
}

# Build a curl config on stdout. printf is a shell builtin, so the secret
# never appears in the process list. Consumed through process substitution.
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

# http_request METHOD URL [extra curl argv...]
# Sets RESP_BODY and RESP_CODE. Returns 0 on a 2xx.
RESP_BODY=""; RESP_CODE=""
http_request() {
  local method="$1" url="$2"; shift 2
  local out
  out="$(curl -K <(cfg_lines "$method" "$url") "$@" -w $'\n%{http_code}' 2>/dev/null || true)"
  RESP_CODE="${out##*$'\n'}"
  RESP_BODY="${out%$'\n'*}"
  if [[ "$RESP_CODE" =~ ^2[0-9][0-9]$ ]]; then return 0; fi
  return 1
}

# Extract a value from a JSON document on stdin.
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

# URL-encode a single component (non-secret inputs only).
urlenc() { python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

# filesize in bytes, portable across BSD (macOS) and GNU stat.
filesize() {
  local f="$1"
  stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || die "cannot stat $f"
}

# =============================================================================
# OPT-IN GUARD (AC2, AC5): refuse to run without explicit opt-in.
# =============================================================================
if [ "${PODBEAN_E2E_TEST:-}" != "1" ]; then
  echo "SKIPPED: Podbean end-to-end integration test requires explicit opt-in."
  echo "Set PODBEAN_E2E_TEST=1 to run this test."
  exit 0
fi

log "opt-in confirmed (PODBEAN_E2E_TEST=1); proceeding with live Podbean integration test"

# ----------------------------------------------------------------- validation --
command -v curl    >/dev/null 2>&1 || die "curl is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"

: "${PODBEAN_CLIENT_ID:?PODBEAN_CLIENT_ID is NOT SET - required for the integration test}"
: "${PODBEAN_CLIENT_SECRET:?PODBEAN_CLIENT_SECRET is NOT SET - required for the integration test}"
: "${PODBEAN_PODCAST_ID:?PODBEAN_PODCAST_ID is NOT SET - required for the integration test}"

# ------------------------------------------------------------------ cleanup --
# Track resources for guaranteed cleanup even on failure.
EPISODE_ID=""        # set after the draft is created
AUDIO_FILE=""        # set after the dummy file is created
CLEANUP_DONE=0

cleanup() {
  if [ "$CLEANUP_DONE" = "1" ]; then return 0; fi
  CLEANUP_DONE=1
  log "cleanup: starting (EPISODE_ID=${EPISODE_ID:-none}, AUDIO_FILE=${AUDIO_FILE:-none})"

  # Delete the test episode if one was created.
  if [ -n "$EPISODE_ID" ] && [ -n "${ACCESS_TOKEN:-}" ]; then
    log "cleanup: deleting test episode ${EPISODE_ID} from Podbean"
    if http_request DELETE "$PODBEAN_API/episodes/${EPISODE_ID}?access_token=${ACCESS_TOKEN}"; then
      log "cleanup: episode ${EPISODE_ID} deleted successfully (HTTP ${RESP_CODE})"
    else
      log "cleanup: WARNING - could not delete episode ${EPISODE_ID} (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
    fi
  fi

  # Remove the temporary audio file.
  if [ -n "$AUDIO_FILE" ] && [ -f "$AUDIO_FILE" ]; then
    rm -f "$AUDIO_FILE"
    log "cleanup: removed temporary audio file ${AUDIO_FILE}"
  fi

  log "cleanup: complete"
}
trap cleanup EXIT

# =============================================================================
# Step 1: Obtain an OAuth access token.
# =============================================================================
log "obtaining Podbean OAuth access token (client_credentials grant)"
ACCESS_TOKEN=""
if ! USE_BASIC=1 http_request POST "$PODBEAN_API/oauth/token" \
  --data-urlencode "grant_type=client_credentials"; then
  die "oauth token request failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
fi
ACCESS_TOKEN="$(printf '%s' "$RESP_BODY" | json_field access_token)"
[ -n "$ACCESS_TOKEN" ] || die "oauth response carried no access_token (HTTP ${RESP_CODE}): $(redact "$RESP_BODY")"
RESP_BODY=""
log "access token acquired (value not shown)"

# =============================================================================
# Step 2: Create a tiny dummy audio file to satisfy Podbean's media requirement.
# =============================================================================
AUDIO_FILE="$(mktemp -t podbean-e2e-test.XXXXXX.mp3)"
python3 -c '
import sys
# MPEG1 Layer3, 128kbps, 44100Hz, stereo frame header + padding
header = bytes([0xFF, 0xFB, 0x90, 0x00])
with open(sys.argv[1], "wb") as f:
    for _ in range(20):
        f.write(header + b"\x00" * 413)
' "$AUDIO_FILE"
log "created dummy audio file: ${AUDIO_FILE} ($(filesize "$AUDIO_FILE") bytes)"

# =============================================================================
# Step 3: Upload the dummy audio via uploadAuthorize + presigned PUT.
# =============================================================================
log "requesting upload authorization for the dummy audio"
AUDIO_FN="$(basename "$AUDIO_FILE")"
AUDIO_CT="audio/mpeg"
AUDIO_SZ="$(filesize "$AUDIO_FILE")"
UPLOAD_URL="$PODBEAN_API/files/uploadAuthorize?access_token=${ACCESS_TOKEN}&content_type=$(urlenc "$AUDIO_CT")&filename=$(urlenc "$AUDIO_FN")&filesize=${AUDIO_SZ}"

if ! http_request GET "$UPLOAD_URL"; then
  die "uploadAuthorize failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
fi
PRESIGNED_URL="$(printf '%s' "$RESP_BODY" | json_field presigned_url)"
MEDIA_KEY="$(printf '%s' "$RESP_BODY" | json_field file_key)"
RESP_BODY=""
[ -n "$PRESIGNED_URL" ] && [ -n "$MEDIA_KEY" ] || die "uploadAuthorize returned no presigned_url or file_key"
log "upload authorized; media_key acquired (value not shown)"

log "uploading dummy audio to presigned URL"
if ! http_request PUT "$PRESIGNED_URL" -T "$AUDIO_FILE" -H "Content-Type: ${AUDIO_CT}"; then
  die "presigned upload failed (HTTP ${RESP_CODE:-000})"
fi
log "dummy audio uploaded successfully (HTTP ${RESP_CODE})"

# Clean up the audio file now; it is on Podbean.
rm -f "$AUDIO_FILE"
AUDIO_FILE=""
log "removed local dummy audio file"

# =============================================================================
# Step 4: Create a DRAFT episode on the target podcast.
# =============================================================================
log "creating draft episode with title: ${TEST_TITLE}"

CREATE_URL="$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}"
CREATE_ARGS=(
  --data-urlencode "podcast_id=${PODBEAN_PODCAST_ID}"
  --data-urlencode "title=${TEST_TITLE}"
  --data-urlencode "content=${TEST_CONTENT}"
  --data-urlencode "status=draft"
  --data-urlencode "type=public"
  --data-urlencode "media_key=${MEDIA_KEY}"
)

if ! http_request POST "$CREATE_URL" "${CREATE_ARGS[@]}"; then
  die "episode create failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
fi

EPISODE_ID="$(printf '%s' "$RESP_BODY" | json_field episode id)"
[ -n "$EPISODE_ID" ] || die "episode created but no id returned (HTTP ${RESP_CODE}): $(redact "$RESP_BODY")"
PERMALINK="$(printf '%s' "$RESP_BODY" | json_field episode permalink_url || true)"
RESP_BODY=""
log "draft episode created: id=${EPISODE_ID} permalink=${PERMALINK:-none}"
echo "  DRAFT CREATED: id=${EPISODE_ID} title=\"${TEST_TITLE}\""

# =============================================================================
# Step 5: Verify the draft episode exists via the API.
# =============================================================================
log "verifying draft episode ${EPISODE_ID} exists on the API"

# List all episodes and find ours.
LIST_URL="$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}&offset=0&limit=50"
if ! http_request GET "$LIST_URL"; then
  die "episode listing failed (HTTP ${RESP_CODE:-000}): $(redact "$RESP_BODY")"
fi

FOUND=""
# Search through the episodes list for our test episode.
FOUND="$(printf '%s' "$RESP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('')
    sys.exit(0)
target = sys.argv[1]
episodes = d.get('episodes', []) if isinstance(d, dict) else []
for ep in episodes:
    if isinstance(ep, dict) and str(ep.get('id', '')) == target:
        print(ep.get('title', ''))
        sys.exit(0)
print('')
" "$EPISODE_ID")"
RESP_BODY=""

if [ -n "$FOUND" ]; then
  log "VERIFIED: draft episode ${EPISODE_ID} exists on Podbean (title: ${FOUND})"
  echo "  VERIFIED: episode exists on Podbean with title \"${FOUND}\""
else
  die "VERIFICATION FAILED: draft episode ${EPISODE_ID} was NOT found in the episode listing"
fi

# =============================================================================
# Step 6: Delete the test episode (proactive cleanup, before trap).
# =============================================================================
log "deleting test episode ${EPISODE_ID}"
SAVED_EPISODE_ID="$EPISODE_ID"
DELETE_URL="$PODBEAN_API/episodes/${SAVED_EPISODE_ID}?access_token=${ACCESS_TOKEN}"
if ! http_request DELETE "$DELETE_URL"; then
  log "WARNING: delete returned HTTP ${RESP_CODE:-000}: $(redact "$RESP_BODY")"
  log "the episode may remain on the podcast; manual cleanup may be needed"
  EPISODE_ID=""
  die "DELETE failed: episode may still exist on Podbean"
fi
log "test episode ${SAVED_EPISODE_ID} deleted successfully (HTTP ${RESP_CODE})"
echo "  DELETED: episode ${SAVED_EPISODE_ID} removed from Podbean"

# Clear EPISODE_ID so the trap does not attempt a second delete.
EPISODE_ID=""

# =============================================================================
# Step 7: Confirm the episode is gone (post-delete verification).
# =============================================================================
log "confirming episode ${SAVED_EPISODE_ID} is no longer on Podbean"

# Re-list episodes and confirm our test episode is absent.
LIST_URL="$PODBEAN_API/episodes?access_token=${ACCESS_TOKEN}&offset=0&limit=50"
if ! http_request GET "$LIST_URL"; then
  # Non-fatal: the delete already succeeded; listing failure does not invalidate.
  log "WARNING: post-delete listing failed (HTTP ${RESP_CODE:-000}); cannot confirm deletion"
else
  STILL_THERE="$(printf '%s' "$RESP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
target = sys.argv[1]
episodes = d.get('episodes', []) if isinstance(d, dict) else []
for ep in episodes:
    if isinstance(ep, dict) and str(ep.get('id', '')) == target:
        print('yes')
        sys.exit(0)
print('')
" "$SAVED_EPISODE_ID")"
  RESP_BODY=""
  if [ -n "$STILL_THERE" ]; then
    log "WARNING: episode ${SAVED_EPISODE_ID} still appears in the listing after delete"
  else
    log "confirmed: episode ${SAVED_EPISODE_ID} is no longer in the episode listing"
  fi
fi

# =============================================================================
# PASS
# =============================================================================
log "PASS: Podbean end-to-end integration test completed successfully"
echo ""
echo "=== Podbean E2E Integration Test: PASS ==="
echo "  Created, verified, and deleted a draft episode on Podbean."
echo "  Podcast ID: ${PODBEAN_PODCAST_ID}"
echo "  Test title: ${TEST_TITLE}"
exit 0

#!/usr/bin/env bash
# =============================================================================
# U040 — Podcast end-to-end publish+verify integration test
#
# Gated integration test that exercises the full Podbean publish+verify+delete
# cycle against a test podcast. Requires explicit opt-in via environment
# variable PODBEAN_INTEGRATION_TEST=1 — never runs unattended.
#
# The test:
#   1. Gates on PODBEAN_INTEGRATION_TEST=1 (opt-in guard)
#   2. Validates required credentials and tools are present
#   3. Generates a minimal valid test mp3 (ffmpeg or built-in fallback)
#   4. Calls podbean_publish.sh --draft to create a draft episode, verify it
#      exists on the API, and delete it — all in one atomic call
#   5. Confirms the output JSON shows draft-verified + deleted=true
#   6. Cleans up after itself (test mp3, temp files) even on failure (trap)
#
# Credential hygiene: credential values are NEVER printed — presence checks
# and probe outcomes only (SET/NOT-SET pattern), mirroring podbean_publish.sh's
# redaction discipline.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PUBLISH_SCRIPT="$HERE/../podbean_publish.sh"

# Resolve platform paths for secrets (mirrors qc-podcast.sh / podbean_publish.sh).
resolve_platform_paths() {
  if [ -d "/data/.openclaw" ]; then
    export SECRETS_ENV="/data/.openclaw/secrets/.env"
  else
    export SECRETS_ENV="$HOME/.openclaw/secrets/.env"
  fi
}
resolve_platform_paths

red()    { printf '\033[31m%s\033[0m\n' "$1" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$1" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$1" >&2; }
log()    { printf '%s U040-integration-test %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }

# --- Opt-in guard ------------------------------------------------------------
if [ "${PODBEAN_INTEGRATION_TEST:-}" != "1" ]; then
  yellow "SKIPPED — PODBEAN_INTEGRATION_TEST is not set to 1."
  echo ""
  echo "This integration test hits the live Podbean API to:"
  echo "  1. Create a draft episode"
  echo "  2. Verify it exists on the API"
  echo "  3. Delete it"
  echo ""
  echo "It requires valid Podbean credentials (PODBEAN_CLIENT_ID,"
  echo "PODBEAN_CLIENT_SECRET, PODBEAN_PODCAST_ID) sourced from your"
  echo "secrets env ($SECRETS_ENV)."
  echo ""
  echo "To opt in and run the full publish+verify+delete cycle:"
  echo "  PODBEAN_INTEGRATION_TEST=1 bash $0"
  exit 0
fi

echo ""
green "═══ U040 — Podcast end-to-end publish+verify integration test ═══"
echo ""

# --- Pre-flight: validate required tools -------------------------------------
command -v curl    >/dev/null 2>&1 || { red "FAIL — curl is required but not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { red "FAIL — python3 is required but not found"; exit 1; }

if [ ! -f "$PUBLISH_SCRIPT" ]; then
  red "FAIL — podbean_publish.sh not found at $PUBLISH_SCRIPT"
  exit 1
fi

# --- Pre-flight: validate podbean_publish.sh syntax --------------------------
log "checking podbean_publish.sh syntax"
if ! bash -n "$PUBLISH_SCRIPT" 2>&1; then
  red "FAIL — podbean_publish.sh failed bash -n syntax check"
  exit 1
fi
green "  OK — podbean_publish.sh passes bash -n"

# --- Load secrets -------------------------------------------------------------
if [ -f "$SECRETS_ENV" ]; then
  set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u
fi

: "${PODBEAN_CLIENT_ID:=}"
: "${PODBEAN_CLIENT_SECRET:=}"
: "${PODBEAN_PODCAST_ID:=}"

# Credential presence checks (values are never printed).
if [ -z "$PODBEAN_CLIENT_ID" ]; then
  red "FAIL — PODBEAN_CLIENT_ID is not set. Source your secrets env or export it."
  exit 1
fi
green "  OK — PODBEAN_CLIENT_ID is set"

if [ -z "$PODBEAN_CLIENT_SECRET" ]; then
  red "FAIL — PODBEAN_CLIENT_SECRET is not set. Source your secrets env or export it."
  exit 1
fi
green "  OK — PODBEAN_CLIENT_SECRET is set"

if [ -z "$PODBEAN_PODCAST_ID" ]; then
  yellow "WARN — PODBEAN_PODCAST_ID is not set. The publish may fail if the broker"
  yellow "       cannot resolve the channel. Set it to the test podcast channel ID."
fi

# --- Temp workspace -----------------------------------------------------------
WORK="$(mktemp -d)"
cleanup() {
  local exit_code=$?
  log "cleaning up temp workspace: $WORK"
  rm -rf "$WORK"
  if [ "$exit_code" -ne 0 ]; then
    red "═══ U040 integration test FAILED (exit code $exit_code) ═══"
  fi
  exit $exit_code
}
trap cleanup EXIT

TEST_MP3="$WORK/test-episode.mp3"
RESULT_FILE="$WORK/result.json"

# --- Generate a minimal valid mp3 ---------------------------------------------
if command -v ffmpeg >/dev/null 2>&1; then
  log "generating test mp3 via ffmpeg (1s silence, mono, 44100 Hz)"
  if ! ffmpeg -f lavfi -i "anullsrc=r=44100:cl=mono" -t 1 -q:a 9 -acodec libmp3lame -y "$TEST_MP3" 2>/dev/null; then
    red "FAIL — ffmpeg could not generate the test mp3"
    exit 1
  fi
else
  log "ffmpeg not found; using built-in base64 minimal mp3 fallback"
  python3 -c '
import base64, sys
blob = base64.b64decode(
    "//uQZAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD/+5DEAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/7kMUAAAAA"
)
with open(sys.argv[1], "wb") as f:
    f.write(blob)
' "$TEST_MP3"
fi

if [ ! -f "$TEST_MP3" ] || [ ! -s "$TEST_MP3" ]; then
  red "FAIL — test mp3 was not created"
  exit 1
fi
green "  OK — test mp3 ready ($(stat -f%z "$TEST_MP3" 2>/dev/null || stat -c%s "$TEST_MP3" 2>/dev/null) bytes)"

# --- Run the publish+verify+delete cycle --------------------------------------
UNIQUE_TITLE="U040-integration-test-$(date -u +%Y%m%dT%H%M%SZ)"
log "running: podbean_publish.sh --draft --audio $TEST_MP3 --title \"$UNIQUE_TITLE\""

set +e
bash "$PUBLISH_SCRIPT" \
  --draft \
  --audio "$TEST_MP3" \
  --title "$UNIQUE_TITLE" \
  --out "$RESULT_FILE" \
  > "$WORK/stdout.log" 2>"$WORK/stderr.log"
PUBLISH_EXIT=$?
set -e

log "podbean_publish.sh exited with code $PUBLISH_EXIT"

if [ "$PUBLISH_EXIT" -ne 0 ]; then
  red "FAIL — podbean_publish.sh --draft exited non-zero (exit code $PUBLISH_EXIT)"
  echo "--- stderr ---"
  sed 's/^/    /' "$WORK/stderr.log" || true
  exit 1
fi

# --- Verify the result JSON --------------------------------------------------
if [ ! -f "$RESULT_FILE" ] || [ ! -s "$RESULT_FILE" ]; then
  red "FAIL — podbean_publish.sh did not produce a result file (--out)"
  exit 1
fi

STATUS="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("status",""))' "$RESULT_FILE")"
DELETED="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print("true" if d.get("deleted") else "false")' "$RESULT_FILE")"
EPISODE_ID="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("episode_id",""))' "$RESULT_FILE")"
EPISODE_NUMBER="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("episode_number",""))' "$RESULT_FILE")"
DRAFT_STATUS="$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("draft_status",""))' "$RESULT_FILE")"

log "result: status=$STATUS deleted=$DELETED episode_id=$EPISODE_ID episode_number=$EPISODE_NUMBER draft_status=$DRAFT_STATUS"

if [ "$STATUS" != "draft-verified" ]; then
  red "FAIL — expected status=draft-verified, got status=$STATUS"
  echo "Full result JSON:"
  sed 's/^/    /' "$RESULT_FILE"
  exit 1
fi
green "  OK — status is draft-verified"

if [ "$DELETED" != "true" ]; then
  red "FAIL — expected deleted=true, got deleted=$DELETED"
  echo "Full result JSON:"
  sed 's/^/    /' "$RESULT_FILE"
  exit 1
fi
green "  OK — episode was deleted after verification"

if [ -z "$EPISODE_ID" ]; then
  red "FAIL — no episode_id in result (create may have failed silently)"
  exit 1
fi
green "  OK — episode_id=$EPISODE_ID (draft was created)"

if [ -z "$EPISODE_NUMBER" ]; then
  red "FAIL — no episode_number in result"
  exit 1
fi
green "  OK — episode_number=$EPISODE_NUMBER"

if [ "$DRAFT_STATUS" != "draft" ]; then
  yellow "WARN — draft_status was \"$DRAFT_STATUS\" (expected \"draft\"); the fetch-back may have failed but the create and delete succeeded"
else
  green "  OK — draft_status=draft (fetch-back confirmed)"
fi

echo ""
green "═══ U040 integration test PASSED ═══"
green "  Created draft episode $EPISODE_ID, verified it, and deleted it."
green "  The full Podbean publish+verify+delete cycle works end-to-end."
exit 0

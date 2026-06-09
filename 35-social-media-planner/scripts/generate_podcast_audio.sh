#!/usr/bin/env bash
# generate_podcast_audio.sh — Skill 35 autonomous podcast audio generation
# Implements the full generate → verify → retry pipeline for Fish Audio S2-Pro.
#
# Usage:
#   bash generate_podcast_audio.sh <script_file> <voice_id> [model] [output_mp3]
#
# Arguments:
#   script_file   — path to the tagged podcast script text file
#   voice_id      — Fish Audio voice/reference ID (FISH_AUDIO_VOICE_ID from secrets/.env)
#   model         — (optional) Fish Audio model; default: s2-pro (current as of 2026-06)
#   output_mp3    — (optional) output path; default: podcast_audio.mp3
#
# Environment:
#   FISH_AUDIO_API_KEY — required; Fish Audio API key from secrets/.env
#
# Exit codes:
#   0   success — audio file verified (exists, non-zero size, valid duration)
#   1   all 3 attempts failed — see stderr for diagnosis
#   2   bad arguments or missing API key
#
# Requirements: curl, ffprobe (bundled with ffmpeg), bash >= 3.2
#
# Fish Audio API reference: https://docs.fish.audio/api-reference/introduction
#   Endpoint:  POST https://api.fish.audio/v1/tts
#   Auth:      Authorization: Bearer <FISH_AUDIO_API_KEY>
#   Model:     via HTTP header: model: s2-pro
#   Response:  binary audio stream (Transfer-Encoding: chunked)

set -euo pipefail

SCRIPT_FILE="${1:-}"
VOICE_ID="${2:-}"
MODEL="${3:-s2-pro}"
OUTPUT_MP3="${4:-podcast_audio.mp3}"

MAX_RETRIES=3
FISH_API_ENDPOINT="https://api.fish.audio/v1/tts"

# --- Argument validation ---
if [[ -z "$SCRIPT_FILE" || -z "$VOICE_ID" ]]; then
  echo "ERROR: Usage: bash generate_podcast_audio.sh <script_file> <voice_id> [model] [output_mp3]" >&2
  echo "  FISH_AUDIO_API_KEY must be set in environment or sourced from secrets/.env" >&2
  exit 2
fi

if [[ ! -f "$SCRIPT_FILE" ]]; then
  echo "ERROR: script file not found: $SCRIPT_FILE" >&2
  exit 2
fi

# Source secrets/.env if API key not already in env
if [[ -z "${FISH_AUDIO_API_KEY:-}" ]]; then
  SECRETS_CANDIDATES=(
    "$HOME/.openclaw/secrets/.env"
    "/data/.openclaw/secrets/.env"
    "$HOME/clawd/secrets/.env"
  )
  for f in "${SECRETS_CANDIDATES[@]}"; do
    if [[ -f "$f" ]] && grep -q "FISH_AUDIO_API_KEY=" "$f" 2>/dev/null; then
      # shellcheck disable=SC1090
      set +u; . "$f"; set -u
      break
    fi
  done
fi

if [[ -z "${FISH_AUDIO_API_KEY:-}" ]]; then
  echo "ERROR: FISH_AUDIO_API_KEY is not set." >&2
  echo "  Set it in secrets/.env or export it before calling this script." >&2
  echo "  Get a key at: https://fish.audio/app/api-keys/" >&2
  exit 2
fi

command -v curl   >/dev/null 2>&1 || { echo "ERROR: curl not installed" >&2; exit 2; }
command -v ffprobe >/dev/null 2>&1 || { echo "ERROR: ffprobe not installed (install ffmpeg)" >&2; exit 2; }

SCRIPT_TEXT="$(cat "$SCRIPT_FILE")"
if [[ -z "$SCRIPT_TEXT" ]]; then
  echo "ERROR: script file is empty: $SCRIPT_FILE" >&2
  exit 2
fi

log()  { printf '[generate_podcast_audio] %s\n' "$*"; }
warn() { printf '[generate_podcast_audio][WARN] %s\n' "$*" >&2; }
err()  { printf '[generate_podcast_audio][ERR ] %s\n' "$*" >&2; }

log "Script file:  $SCRIPT_FILE"
log "Voice ID:     $VOICE_ID"
log "Model:        $MODEL"
log "Output:       $OUTPUT_MP3"
log "API endpoint: $FISH_API_ENDPOINT"

# Build JSON payload using python3 for safe escaping
PAYLOAD_FILE="$(mktemp)"
trap 'rm -f "$PAYLOAD_FILE"' EXIT

python3 - "$SCRIPT_TEXT" "$VOICE_ID" > "$PAYLOAD_FILE" <<'PYEOF'
import json, sys
text = sys.argv[1]
voice_id = sys.argv[2]
payload = {
    "text": text,
    "reference_id": voice_id,
    "format": "mp3",
    "latency": "normal",
    "normalize": True,
    "chunk_length": 300
}
print(json.dumps(payload))
PYEOF

log "Payload built ($(wc -c < "$PAYLOAD_FILE") bytes)"

# --- Retry loop ---
ATTEMPT=0
LAST_HTTP_CODE=""
LAST_ERROR=""

while [[ $ATTEMPT -lt $MAX_RETRIES ]]; do
  ATTEMPT=$((ATTEMPT + 1))
  log "Attempt $ATTEMPT of $MAX_RETRIES..."

  HTTP_CODE=$(curl -sS -w "%{http_code}" -o "$OUTPUT_MP3" \
    --max-time 120 \
    -X POST "$FISH_API_ENDPOINT" \
    -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
    -H "Content-Type: application/json" \
    -H "model: $MODEL" \
    -d @"$PAYLOAD_FILE" \
    2>&1) || CURL_EXIT=$?
  LAST_HTTP_CODE="$HTTP_CODE"

  # Evaluate result
  if [[ "$HTTP_CODE" == "200" ]]; then
    # Verify file exists and is non-zero
    if [[ ! -f "$OUTPUT_MP3" ]] || [[ ! -s "$OUTPUT_MP3" ]]; then
      LAST_ERROR="HTTP 200 but output file is missing or empty: $OUTPUT_MP3"
      err "$LAST_ERROR"
    else
      # ffprobe duration check
      DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT_MP3" 2>/dev/null || echo "0")
      DURATION_INT=$(echo "$DURATION" | awk '{printf "%d", $1}')
      if [[ "$DURATION_INT" -lt 30 ]]; then
        LAST_ERROR="Audio file duration ${DURATION}s is suspiciously short (< 30s) — possible generation failure"
        err "$LAST_ERROR"
        # Continue to retry
      else
        log "SUCCESS — audio verified: $OUTPUT_MP3"
        log "  Duration:  ${DURATION}s"
        log "  File size: $(wc -c < "$OUTPUT_MP3") bytes"
        exit 0
      fi
    fi
  else
    # Non-200 — read any error body that was written to the output file
    BODY=""
    if [[ -f "$OUTPUT_MP3" ]]; then
      BODY="$(cat "$OUTPUT_MP3" 2>/dev/null || true)"
      rm -f "$OUTPUT_MP3"
    fi
    LAST_ERROR="HTTP $HTTP_CODE from Fish Audio API. Body: ${BODY:0:300}"
    err "$LAST_ERROR"

    # Diagnose common failure modes
    case "$HTTP_CODE" in
      401)
        err "DIAGNOSIS: 401 Unauthorized — FISH_AUDIO_API_KEY is invalid or expired."
        err "  Verify the key at https://fish.audio/app/api-keys/"
        ;;
      403)
        err "DIAGNOSIS: 403 Forbidden — account may lack TTS access or key has wrong scope."
        ;;
      404)
        err "DIAGNOSIS: 404 — voice_id '$VOICE_ID' may be invalid or deleted."
        err "  Verify FISH_AUDIO_VOICE_ID in secrets/.env against your Fish Audio voice library."
        ;;
      422)
        err "DIAGNOSIS: 422 Unprocessable — request body malformed. Check script text for invalid characters."
        ;;
      429)
        err "DIAGNOSIS: 429 Rate limited — too many requests. Waiting 15 seconds before retry..."
        sleep 15
        ;;
      503|504)
        err "DIAGNOSIS: ${HTTP_CODE} — Fish Audio service temporarily unavailable. Waiting 10 seconds..."
        sleep 10
        ;;
      000)
        err "DIAGNOSIS: Network error (HTTP 000) — no connection to api.fish.audio."
        err "  Check network connectivity on this box."
        ;;
    esac
  fi

  if [[ $ATTEMPT -lt $MAX_RETRIES ]]; then
    log "Waiting 5 seconds before retry $((ATTEMPT + 1))..."
    sleep 5
  fi
done

# --- All retries exhausted ---
err "=== ALL $MAX_RETRIES ATTEMPTS FAILED ==="
err "Last HTTP code:  $LAST_HTTP_CODE"
err "Last error:      $LAST_ERROR"
err ""
err "DIAGNOSTIC CHECKLIST:"
err "  1. FISH_AUDIO_API_KEY — is it set and valid?"
err "     Test: curl -sS -H \"Authorization: Bearer \$FISH_AUDIO_API_KEY\" https://api.fish.audio/v1/me"
err "  2. FISH_AUDIO_VOICE_ID — is '$VOICE_ID' a valid voice ID in this account?"
err "     Test: curl -sS -H \"Authorization: Bearer \$FISH_AUDIO_API_KEY\" https://api.fish.audio/v1/model/$VOICE_ID"
err "  3. Model — is '$MODEL' available? (current recommended: s2-pro)"
err "  4. Network — can this box reach api.fish.audio?"
err "     Test: curl -sS -o /dev/null -w '%{http_code}' https://api.fish.audio/v1/me"
err "  5. Script text — is the script file readable and non-empty?"
err "     File: $SCRIPT_FILE ($(wc -c < "$SCRIPT_FILE" 2>/dev/null || echo '?') bytes)"
err ""
err "The agent must NOT fall back to client self-recording until all 3 retries"
err "are exhausted AND the operator has been notified via Telegram with these details."
exit 1

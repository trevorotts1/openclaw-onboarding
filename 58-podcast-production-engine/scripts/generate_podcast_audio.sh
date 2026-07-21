#!/usr/bin/env bash
# generate_podcast_audio.sh, Podcast Production Engine (Skill 58) Step 11 render module.
#
# Adapted from Skill 35 scripts/generate_podcast_audio.sh (the proven generate,
# verify, retry pipeline) per PRD Step 11 and reuse map Section 7.2. What this
# module adds over the Skill 35 base:
#   - Fish Audio model s2.1-pro selected via the HTTP header "model:" (LIVE-VERIFIED
#     accepted by POST https://api.fish.audio/v1/tts at build time on 2026-07-06:
#     HTTP 200, content-type audio/mpeg).
#   - The client's OWN reference_id is required (one private voice model per client).
#   - Output MP3 at 192 kbps (mp3_bitrate 192, LIVE-VERIFIED at build time).
#   - condition_on_previous_chunks true so long chunked synthesis stays consistent.
#   - Splitting at NATURAL BEAT boundaries only (paragraph breaks, else sentence
#     boundaries), never mid-sentence and never inside a square-bracket delivery tag,
#     with a fail-closed bracket-balance assertion per segment.
#   - ffmpeg seamless join of the rendered segments.
#   - Loudness mastering to the Skill 23 doctrine of minus 14 to minus 16 LUFS
#     integrated (two-pass loudnorm, target minus 15), then ffprobe plus EBU R128
#     verification that the master lands inside the doctrine band.
#   - Structural refusal of the free tier (s2.1-pro-free) for client content: it
#     carries no service level agreement and may train on inputs.
#
# Secrecy: the Fish Audio API key is reported as SET or NOT SET only; its value is
# never printed, echoed, or written to any output.
#
# Usage:
#   bash generate_podcast_audio.sh <script_file> <reference_id> [model] [output_mp3] [client_name] [episode_title]
#
# Arguments (positions 1 to 4 are compatible with the Skill 35 base):
#   script_file    path to the tagged Final Draft podcast script text file
#   reference_id   the client's OWN Fish Audio voice reference_id (required)
#   model          (optional) Fish Audio backbone model; default s2.1-pro; any
#                  "*-free" model is structurally refused for client content
#   output_mp3     (optional) explicit output path; default podcast_audio.mp3, or
#                  derived as "<client_name> - <episode_title>.mp3" when both are given
#   client_name    (optional) client name, placed FIRST in the derived filename
#   episode_title  (optional) episode title, placed after the client name
#
# Environment:
#   FISH_AUDIO_API_KEY        required; resolved from env or the client secret stores
#   FISH_MP3_BITRATE          optional; default 192
#   PODCAST_LUFS_TARGET       optional; default -15 (must resolve inside -16..-14)
#   FISH_MAX_SEGMENT_BYTES    optional; per-request UTF-8 byte cap that triggers a
#                             natural-beat split; default 20000 (a 10 minute episode
#                             at ~8000 bytes stays a single segment)
#   FISH_CHUNK_LENGTH         optional; per-request internal chunk_length; default 300
#   PODCAST_MIN_DURATION      optional; minimum acceptable total seconds; default 30
#
# Exit codes:
#   0  success, mastered audio verified (exists, non-zero, duration and loudness sane)
#   1  a Fish Audio render segment failed after all retries, or mastering or
#      verification failed
#   2  bad arguments, missing key, missing dependency, or a forbidden free-tier model
#
# Requirements: curl, python3, ffmpeg, ffprobe (ffprobe ships with ffmpeg), bash >= 3.2
#
# Fish Audio API reference: https://docs.fish.audio/api-reference/introduction
#   Endpoint: POST https://api.fish.audio/v1/tts
#   Auth:     Authorization: Bearer <FISH_AUDIO_API_KEY>
#   Model:    via HTTP header "model: s2.1-pro"
#   Response: binary audio stream (Transfer-Encoding: chunked)

set -euo pipefail

SCRIPT_FILE="${1:-}"
REFERENCE_ID="${2:-}"
MODEL="${3:-s2.1-pro}"
OUTPUT_MP3="${4:-}"
CLIENT_NAME="${5:-}"
EPISODE_TITLE="${6:-}"

MAX_RETRIES=3
FISH_API_ENDPOINT="https://api.fish.audio/v1/tts"
FISH_MP3_BITRATE="${FISH_MP3_BITRATE:-192}"
PODCAST_LUFS_TARGET="${PODCAST_LUFS_TARGET:--15}"
FISH_MAX_SEGMENT_BYTES="${FISH_MAX_SEGMENT_BYTES:-20000}"
FISH_CHUNK_LENGTH="${FISH_CHUNK_LENGTH:-300}"
PODCAST_MIN_DURATION="${PODCAST_MIN_DURATION:-30}"

# Loudness doctrine band (Skill 23): integrated loudness must land inside minus 16
# to minus 14 LUFS. A small measurement tolerance is allowed on the verify step.
LUFS_BAND_LOW="-16"
LUFS_BAND_HIGH="-14"
LUFS_VERIFY_LOW="-16.5"
LUFS_VERIFY_HIGH="-13.5"

log()  { printf '[generate_podcast_audio] %s\n' "$*"; }
warn() { printf '[generate_podcast_audio][WARN] %s\n' "$*" >&2; }
err()  { printf '[generate_podcast_audio][ERR ] %s\n' "$*" >&2; }

# --- Argument validation ---
if [[ -z "$SCRIPT_FILE" || -z "$REFERENCE_ID" ]]; then
  err "Usage: bash generate_podcast_audio.sh <script_file> <reference_id> [model] [output_mp3] [client_name] [episode_title]"
  err "  reference_id is the client's OWN Fish Audio voice model; it is required."
  err "  FISH_AUDIO_API_KEY must be set in the environment or a client secret store."
  exit 2
fi

if [[ ! -f "$SCRIPT_FILE" ]]; then
  err "script file not found: $SCRIPT_FILE"
  exit 2
fi

# --- Free-tier structural refusal (client content) ---
# s2.1-pro-free has no service level agreement and may train on inputs. It is
# forbidden for production client content and refused here before any network call.
MODEL_LC="$(printf '%s' "$MODEL" | tr '[:upper:]' '[:lower:]')"
case "$MODEL_LC" in
  *-free|*free)
    err "REFUSED: model '$MODEL' is a free tier. The free tier carries no service"
    err "  level agreement and may train on inputs, so it is forbidden for client"
    err "  content. Use the paid model s2.1-pro with the client's own reference_id."
    exit 2
    ;;
esac

# --- Fish Audio key resolution (value never printed) ---
if [[ -z "${FISH_AUDIO_API_KEY:-}" ]]; then
  SECRETS_CANDIDATES=(
    "$HOME/.openclaw/secrets/.env"
    "/data/.openclaw/secrets/.env"
    "$HOME/clawd/secrets/.env"
  )
  for f in "${SECRETS_CANDIDATES[@]}"; do
    if [[ -f "$f" ]] && grep -q "FISH_AUDIO_API_KEY=" "$f" 2>/dev/null; then
      set +u
      # shellcheck disable=SC1090
      . "$f"
      set -u
      break
    fi
  done
fi

if [[ -z "${FISH_AUDIO_API_KEY:-}" ]]; then
  err "FISH_AUDIO_API_KEY: NOT SET."
  err "  Set it in a client secret store or export it before calling this script."
  err "  The client's OWN Fish Audio key is required; no shared or operator key."
  exit 2
fi
log "FISH_AUDIO_API_KEY: SET"

# --- Dependencies ---
command -v curl    >/dev/null 2>&1 || { err "curl not installed"; exit 2; }
command -v python3 >/dev/null 2>&1 || { err "python3 not installed"; exit 2; }
command -v ffmpeg  >/dev/null 2>&1 || { err "ffmpeg not installed"; exit 2; }
command -v ffprobe >/dev/null 2>&1 || { err "ffprobe not installed (install ffmpeg)"; exit 2; }

# --- Loudness target sanity: must resolve inside the doctrine band ---
if ! python3 - "$PODCAST_LUFS_TARGET" "$LUFS_BAND_LOW" "$LUFS_BAND_HIGH" <<'PYEOF'
import sys
t, lo, hi = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
sys.exit(0 if lo <= t <= hi else 1)
PYEOF
then
  err "PODCAST_LUFS_TARGET '$PODCAST_LUFS_TARGET' is outside the doctrine band ${LUFS_BAND_LOW}..${LUFS_BAND_HIGH} LUFS."
  exit 2
fi

SCRIPT_TEXT="$(cat "$SCRIPT_FILE")"
if [[ -z "${SCRIPT_TEXT// }" ]]; then
  err "script file is empty: $SCRIPT_FILE"
  exit 2
fi

# --- Resolve the output filename (client name FIRST, then episode title) ---
if [[ -z "$OUTPUT_MP3" ]]; then
  if [[ -n "$CLIENT_NAME" && -n "$EPISODE_TITLE" ]]; then
    OUTPUT_MP3="$(python3 - "$CLIENT_NAME" "$EPISODE_TITLE" <<'PYEOF'
import re, sys
def clean(s):
    s = re.sub(r'[^0-9A-Za-z()\- _]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
name = clean(sys.argv[1]); title = clean(sys.argv[2])
print(f"{name} - {title}.mp3" if name and title else "podcast_audio.mp3")
PYEOF
)"
  else
    OUTPUT_MP3="podcast_audio.mp3"
  fi
fi

log "Script file:   $SCRIPT_FILE"
log "Reference id:  (client voice model, set)"
log "Model:         $MODEL"
log "Bitrate:       ${FISH_MP3_BITRATE}k"
log "Loudness:      target ${PODCAST_LUFS_TARGET} LUFS (band ${LUFS_BAND_LOW}..${LUFS_BAND_HIGH})"
log "Output:        $OUTPUT_MP3"
log "API endpoint:  $FISH_API_ENDPOINT"

# --- Working directory ---
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# --- Segment the script at natural beat boundaries ---
# Splitting rule: prefer paragraph breaks (a blank line, the Final Draft natural
# beat). If one paragraph alone exceeds the per-request byte cap, fall back to
# sentence boundaries. NEVER split inside a square-bracket delivery tag, and NEVER
# split mid-sentence. Each emitted segment is asserted bracket-balanced (fail
# closed) so no orphaned or malformed tag can ever be sent to Fish Audio.
SEG_DIR="$WORKDIR/segments"
mkdir -p "$SEG_DIR"
SCRIPT_INPUT="$WORKDIR/script_input.txt"
printf '%s' "$SCRIPT_TEXT" > "$SCRIPT_INPUT"

SEG_COUNT="$(python3 - "$SEG_DIR" "$FISH_MAX_SEGMENT_BYTES" "$SCRIPT_INPUT" <<'PYEOF'
import os, re, sys

seg_dir = sys.argv[1]
max_bytes = int(sys.argv[2])
text = open(sys.argv[3], "r", encoding="utf-8").read()

def blen(s):
    return len(s.encode("utf-8"))

def split_sentences(paragraph):
    # Split after . ! ? followed by whitespace, but only when bracket depth is
    # zero so a delivery tag such as [long pause] is never cut. This keeps every
    # piece whole at the sentence level: we never break mid-sentence.
    pieces, buf, depth = [], [], 0
    chars = list(paragraph)
    for i, ch in enumerate(chars):
        buf.append(ch)
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif ch in ".!?" and depth == 0:
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == "" or nxt.isspace():
                pieces.append("".join(buf).strip())
                buf = []
    tail = "".join(buf).strip()
    if tail:
        pieces.append(tail)
    return [p for p in pieces if p]

# Natural beats first: paragraphs separated by one or more blank lines.
paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]

# Break any oversized paragraph down to sentence granularity.
units = []
for para in paragraphs:
    if blen(para) <= max_bytes:
        units.append(para)
    else:
        for sent in split_sentences(para):
            units.append(sent)

# Greedily pack units into segments under the byte cap, joining paragraph-level
# units with a blank line so Fish keeps the natural pause between beats.
segments, cur, cur_bytes = [], [], 0
for u in units:
    ub = blen(u)
    joiner = 2 if cur else 0  # the "\n\n" we will insert between units
    if cur and cur_bytes + joiner + ub > max_bytes:
        segments.append("\n\n".join(cur))
        cur, cur_bytes = [u], ub
    else:
        cur.append(u)
        cur_bytes += joiner + ub
if cur:
    segments.append("\n\n".join(cur))

if not segments:
    sys.stderr.write("no renderable text after segmentation\n")
    sys.exit(3)

# Fail closed: every segment must be bracket-balanced with no negative depth at
# any point. A malformed tag is a hard error, never sent to the API.
for idx, seg in enumerate(segments):
    depth = 0
    for ch in seg:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                sys.stderr.write(f"segment {idx} has an unbalanced closing bracket\n")
                sys.exit(4)
    if depth != 0:
        sys.stderr.write(f"segment {idx} has an unbalanced opening bracket\n")
        sys.exit(4)
    with open(os.path.join(seg_dir, f"seg_{idx:04d}.txt"), "w", encoding="utf-8") as fh:
        fh.write(seg)

print(len(segments))
PYEOF
)" || { err "segmentation failed (unbalanced tag or empty script)"; exit 1; }

log "Segments:      $SEG_COUNT (natural-beat split at ${FISH_MAX_SEGMENT_BYTES} byte cap)"

# --- Render each segment with the Skill 35 retry-plus-verify pattern ---
render_segment() {
  local seg_txt="$1" seg_mp3="$2" seg_label="$3"
  local seg_text payload_file attempt http_code last_error curl_exit duration duration_int body

  seg_text="$(cat "$seg_txt")"
  payload_file="$WORKDIR/payload_${seg_label}.json"

  python3 - "$seg_text" "$REFERENCE_ID" "$FISH_MP3_BITRATE" "$FISH_CHUNK_LENGTH" > "$payload_file" <<'PYEOF'
import json, sys
text, reference_id = sys.argv[1], sys.argv[2]
mp3_bitrate, chunk_length = int(sys.argv[3]), int(sys.argv[4])
payload = {
    "text": text,
    "reference_id": reference_id,
    "format": "mp3",
    "mp3_bitrate": mp3_bitrate,
    "latency": "normal",
    "normalize": True,
    "chunk_length": chunk_length,
    "condition_on_previous_chunks": True,
}
print(json.dumps(payload))
PYEOF

  attempt=0
  last_error=""
  while [[ $attempt -lt $MAX_RETRIES ]]; do
    attempt=$((attempt + 1))
    log "  segment ${seg_label}: attempt ${attempt} of ${MAX_RETRIES}"

    curl_exit=0
    http_code=$(curl -sS -w "%{http_code}" -o "$seg_mp3" \
      --max-time 180 \
      -X POST "$FISH_API_ENDPOINT" \
      -H "Authorization: Bearer $FISH_AUDIO_API_KEY" \
      -H "Content-Type: application/json" \
      -H "model: $MODEL" \
      -d @"$payload_file") || curl_exit=$?

    if [[ "$http_code" == "200" ]]; then
      if [[ ! -s "$seg_mp3" ]]; then
        last_error="HTTP 200 but segment output is missing or empty"
        err "  $last_error"
      else
        duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$seg_mp3" 2>/dev/null || echo "0")
        duration_int=$(printf '%.0f' "${duration:-0}" 2>/dev/null || echo 0)
        if [[ "$duration_int" -le 0 ]]; then
          last_error="segment ${seg_label} has no decodable audio (duration ${duration}s)"
          err "  $last_error"
        else
          log "  segment ${seg_label}: rendered ${duration}s"
          return 0
        fi
      fi
    else
      body=""
      if [[ -f "$seg_mp3" ]]; then
        body="$(head -c 300 "$seg_mp3" 2>/dev/null || true)"
        rm -f "$seg_mp3"
      fi
      last_error="HTTP ${http_code} (curl exit ${curl_exit}) from Fish Audio. Body: ${body}"
      err "  $last_error"
      case "$http_code" in
        401) err "  DIAGNOSIS: 401 Unauthorized. The client's FISH_AUDIO_API_KEY is invalid or expired." ;;
        402) err "  DIAGNOSIS: 402 Payment required. The client's Fish Audio wallet is out of credit." ;;
        403) err "  DIAGNOSIS: 403 Forbidden. The account lacks TTS access or the key scope is wrong." ;;
        404) err "  DIAGNOSIS: 404. The reference_id may be invalid or deleted for this account." ;;
        422) err "  DIAGNOSIS: 422 Unprocessable. Request body malformed; check the script text." ;;
        429) err "  DIAGNOSIS: 429 Rate limited. Waiting 15 seconds before retry."; sleep 15 ;;
        503|504) err "  DIAGNOSIS: ${http_code}. Fish Audio temporarily unavailable. Waiting 10 seconds."; sleep 10 ;;
        000) err "  DIAGNOSIS: network error (HTTP 000). No connection to api.fish.audio." ;;
      esac
    fi

    if [[ $attempt -lt $MAX_RETRIES ]]; then
      log "  waiting 5 seconds before retry"
      sleep 5
    fi
  done

  err "segment ${seg_label} FAILED after ${MAX_RETRIES} attempts. Last error: ${last_error}"
  return 1
}

CONCAT_LIST="$WORKDIR/concat.txt"
: > "$CONCAT_LIST"
idx=0
while [[ $idx -lt $SEG_COUNT ]]; do
  label="$(printf '%04d' "$idx")"
  seg_txt="$SEG_DIR/seg_${label}.txt"
  seg_mp3="$WORKDIR/seg_${label}.mp3"
  if ! render_segment "$seg_txt" "$seg_mp3" "$label"; then
    err "=== RENDER FAILED at segment ${label}; no partial audio is delivered ==="
    err "  The agent must NOT fall back to client self-recording until all retries"
    err "  are exhausted AND the operator has been notified with these details."
    exit 1
  fi
  printf "file '%s'\n" "$seg_mp3" >> "$CONCAT_LIST"
  idx=$((idx + 1))
done

# --- Seamless join into a single lossless intermediate ---
JOINED_WAV="$WORKDIR/joined.wav"
log "Joining ${SEG_COUNT} segment(s) seamlessly"
if ! ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$CONCAT_LIST" \
    -c:a pcm_s16le -ar 44100 "$JOINED_WAV" </dev/null; then
  err "ffmpeg join failed"
  exit 1
fi

# --- Master to the Skill 23 loudness doctrine (two-pass loudnorm) ---
log "Mastering to ${PODCAST_LUFS_TARGET} LUFS integrated (two-pass loudnorm)"
MEASURE_LOG="$WORKDIR/loudnorm_measure.json"
ffmpeg -hide_banner -loglevel info -i "$JOINED_WAV" \
  -af "loudnorm=I=${PODCAST_LUFS_TARGET}:LRA=11:TP=-1.5:print_format=json" \
  -f null - </dev/null 2>"$MEASURE_LOG" || { err "loudnorm measurement pass failed"; exit 1; }

# Extract the measured values from the loudnorm JSON block in the ffmpeg log.
LN_FILTER="$(python3 - "$MEASURE_LOG" "$PODCAST_LUFS_TARGET" <<'PYEOF'
import json, re, sys
raw = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
target = sys.argv[2]
matches = re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", raw, re.DOTALL)
if not matches:
    sys.stderr.write("could not locate loudnorm JSON in the measurement log\n")
    sys.exit(1)
d = json.loads(matches[-1])
print(
    "loudnorm=I=%s:LRA=11:TP=-1.5:"
    "measured_I=%s:measured_LRA=%s:measured_TP=%s:measured_thresh=%s:"
    "offset=%s:linear=true:print_format=summary"
    % (target, d["input_i"], d["input_lra"], d["input_tp"],
       d["input_thresh"], d["target_offset"])
)
PYEOF
)" || { err "failed to parse loudnorm measurement"; exit 1; }

if ! ffmpeg -hide_banner -loglevel error -y -i "$JOINED_WAV" \
    -af "$LN_FILTER" \
    -c:a libmp3lame -b:a "${FISH_MP3_BITRATE}k" -ar 44100 "$OUTPUT_MP3" </dev/null; then
  err "loudnorm mastering pass failed"
  exit 1
fi

# --- Verify the master (existence, size, duration, integrated loudness) ---
if [[ ! -s "$OUTPUT_MP3" ]]; then
  err "master output is missing or empty: $OUTPUT_MP3"
  exit 1
fi

FINAL_DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT_MP3" 2>/dev/null || echo "0")
FINAL_DURATION_INT=$(printf '%.0f' "${FINAL_DURATION:-0}" 2>/dev/null || echo 0)
if [[ "$FINAL_DURATION_INT" -lt "$PODCAST_MIN_DURATION" ]]; then
  err "master duration ${FINAL_DURATION}s is below the minimum ${PODCAST_MIN_DURATION}s; treating as a render failure"
  exit 1
fi

# Measure the integrated loudness of the master with EBU R128 and confirm it lands
# inside the doctrine band (with a small measurement tolerance).
R128_LOG="$WORKDIR/r128_verify.log"
# T0-20: the measurement's exit status IS part of the verdict. This was
# `... || true`, so a failed ffmpeg run left an empty/partial log, the parse
# returned NA, the NA branch below only warned, and the script reached
# "SUCCESS, mastered audio verified" and exited 0 — releasing an UNMEASURED
# master to a client feed with a success record behind it. The header contract
# at the top of this file states that exit 0 means duration AND loudness are
# sane, so an unmeasurable master must fail, not warn.
R128_RC=0
ffmpeg -hide_banner -nostats -i "$OUTPUT_MP3" -af ebur128 -f null - </dev/null 2>"$R128_LOG" || R128_RC=$?
if [[ "$R128_RC" -ne 0 ]]; then
  err "loudness measurement failed (ffmpeg -af ebur128 exit ${R128_RC}); the master is UNMEASURED and cannot be reported verified. Log: $R128_LOG"
  exit 1
fi
MEASURED_LUFS="$(python3 - "$R128_LOG" <<'PYEOF'
import re, sys
raw = open(sys.argv[1], "r", encoding="utf-8", errors="replace").read()
# The ebur128 summary block ends with a line like "    I:         -15.0 LUFS".
m = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", raw)
print(m[-1] if m else "NA")
PYEOF
)"

if [[ "$MEASURED_LUFS" == "NA" ]]; then
  # T0-20: an unparseable summary is an UNMEASURED master, not a measured-and-fine
  # one. A duration check says nothing about loudness.
  err "could not parse an integrated-loudness summary from the EBU R128 measurement; the master is UNMEASURED and cannot be reported verified. Log: $R128_LOG"
  exit 1
else
  if python3 - "$MEASURED_LUFS" "$LUFS_VERIFY_LOW" "$LUFS_VERIFY_HIGH" <<'PYEOF'
import sys
v, lo, hi = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
sys.exit(0 if lo <= v <= hi else 1)
PYEOF
  then
    log "Loudness verified: ${MEASURED_LUFS} LUFS integrated (doctrine band ${LUFS_BAND_LOW}..${LUFS_BAND_HIGH})"
  else
    err "master integrated loudness ${MEASURED_LUFS} LUFS is outside the doctrine band ${LUFS_BAND_LOW}..${LUFS_BAND_HIGH}"
    exit 1
  fi
fi

log "SUCCESS, mastered audio verified: $OUTPUT_MP3"
log "  Model:     $MODEL (paid tier, client reference_id)"
log "  Segments:  $SEG_COUNT"
log "  Duration:  ${FINAL_DURATION}s"
log "  Loudness:  ${MEASURED_LUFS} LUFS integrated"
log "  Bitrate:   ${FISH_MP3_BITRATE}k"
log "  File size: $(wc -c < "$OUTPUT_MP3") bytes"
exit 0

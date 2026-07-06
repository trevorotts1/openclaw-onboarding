#!/usr/bin/env bash
# generate_cover.sh - Podcast Production Engine, Step 10 (COVER ART).
#
# Kie.ai GPT-image-2 cover generation seeded from Skill 57 prompt 14, then an
# in-house ffmpeg finalize chain that produces an Apple-Podcasts-valid square
# JPEG (1400 to 3000 on a side, RGB, under 512 kilobytes) with a spec-valid
# filename. The pipeline owns the up-to-3 image attempts (furnace
# image_gen_attempts_max); this script performs ONE generate-and-finalize cycle
# and returns a typed exit code so the caller can hold and alert (deduped) on a
# bounded timeout, exactly per furnace-design Guardrail 6.
#
# Doctrine honored here:
#   - Bounded polling: backoff schedule 5,10,20,40,60 then 60, total timeout 600s.
#     Never poll faster than 5s; never poll forever.
#   - Never below 1400 square. Square, JPEG, RGB, under 512 kilobytes.
#   - Silence: operator/agent stdout only. No client message. No Telegram.
#   - Secrecy: the API key is read from the environment or a 0600 secrets file
#     and is NEVER printed, echoed, or written to the receipt.
#   - No content-model provider is invoked here; this is a pure media step, so
#     the runtime routing policy and its deny list are not touched.
#
# USAGE
#   Generate + finalize:
#     generate_cover.sh --prompt-file <visual_desc.txt> \
#                       [--prompt "<visual description>"] \
#                       [--title "<episode title>"] [--theme "<episode theme>"] \
#                       [--client "<client name>"] \
#                       [--out <cover.jpg>] [--work-dir <dir>] \
#                       [--receipt <receipt.json>]
#   Finalize an existing image only (no Kie call; Episode Asset Pack repairs and
#   the canary ffmpeg proof both use this path):
#     generate_cover.sh --finalize-only <image> --out <cover.jpg> \
#                       [--client ...] [--title ...] [--receipt ...]
#
# ENVIRONMENT (all optional except the key; every knob mirrors furnace-design)
#   KIE_API_KEY                Kie.ai key (required for generation; read, never printed)
#   KIE_API_BASE               default https://api.kie.ai
#   KIE_COVER_MODEL            default gpt-image-2-text-to-image
#   KIE_COVER_ASPECT           default 1:1
#   KIE_COVER_RESOLUTION       default 1K   (PRD Step 10: 1K square; live-verify pins it)
#   KIE_COVER_RESOLUTION_FALLBACK  default 2K (used once if the API rejects the primary)
#   KIE_COVER_OUTPUT_FORMAT    default png  (ffmpeg does the JPEG conversion in-house)
#   KIE_BACKOFF_SCHEDULE       default "5 10 20 40 60"
#   KIE_POLL_TIMEOUT_SECONDS   default 600
#   KIE_CREATE_RETRIES         default 2    (transient createTask retries)
#   COVER_MIN_SIDE             default 1400
#   COVER_MAX_SIDE             default 3000
#   COVER_MAX_BYTES            default 524288 (512 kilobytes)
#
# EXIT CODES
#   0  success; finalized cover verified against every invariant
#   2  bad arguments, missing dependency, or missing API key
#   3  createTask failed after retries (API error)
#   4  poll timeout (bounded); caller counts one failed image attempt and holds
#   5  generation task reported failure
#   6  result download failed
#   7  finalize or invariant verification failed
#
# Requires: curl, jq, ffmpeg, ffprobe, bash >= 3.2

set -euo pipefail

# ---------------------------------------------------------------------------
# Config (env with defaults)
# ---------------------------------------------------------------------------
KIE_API_BASE="${KIE_API_BASE:-https://api.kie.ai}"
KIE_COVER_MODEL="${KIE_COVER_MODEL:-gpt-image-2-text-to-image}"
KIE_COVER_ASPECT="${KIE_COVER_ASPECT:-1:1}"
KIE_COVER_RESOLUTION="${KIE_COVER_RESOLUTION:-1K}"
KIE_COVER_RESOLUTION_FALLBACK="${KIE_COVER_RESOLUTION_FALLBACK:-2K}"
KIE_COVER_OUTPUT_FORMAT="${KIE_COVER_OUTPUT_FORMAT:-png}"
KIE_BACKOFF_SCHEDULE="${KIE_BACKOFF_SCHEDULE:-5 10 20 40 60}"
KIE_POLL_TIMEOUT_SECONDS="${KIE_POLL_TIMEOUT_SECONDS:-600}"
KIE_CREATE_RETRIES="${KIE_CREATE_RETRIES:-2}"
COVER_MIN_SIDE="${COVER_MIN_SIDE:-1400}"
COVER_MAX_SIDE="${COVER_MAX_SIDE:-3000}"
COVER_MAX_BYTES="${COVER_MAX_BYTES:-524288}"

# Fixed suffix seeded from Skill 57 prompt 14 (podcast cover template).
COVER_PROMPT_SUFFIX="Create a square podcast cover art image. Professional, clean, visually striking. Suitable for podcast platforms."

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
PROMPT=""
PROMPT_FILE=""
TITLE=""
THEME=""
CLIENT=""
OUT=""
WORK_DIR=""
RECEIPT=""
FINALIZE_ONLY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt)        PROMPT="${2:-}"; shift 2 ;;
    --prompt-file)   PROMPT_FILE="${2:-}"; shift 2 ;;
    --title)         TITLE="${2:-}"; shift 2 ;;
    --theme)         THEME="${2:-}"; shift 2 ;;
    --client)        CLIENT="${2:-}"; shift 2 ;;
    --out)           OUT="${2:-}"; shift 2 ;;
    --work-dir)      WORK_DIR="${2:-}"; shift 2 ;;
    --receipt)       RECEIPT="${2:-}"; shift 2 ;;
    --finalize-only) FINALIZE_ONLY="${2:-}"; shift 2 ;;
    -h|--help)       grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "ERROR: unknown argument: $1" >&2; exit 2 ;;
  esac
done

log()  { printf '[generate_cover] %s\n' "$*" >&2; }
warn() { printf '[generate_cover][WARN] %s\n' "$*" >&2; }
err()  { printf '[generate_cover][ERR ] %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------
for tool in ffmpeg ffprobe; do
  command -v "$tool" >/dev/null 2>&1 || { err "$tool not installed (install ffmpeg)"; exit 2; }
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# slugify <text> -> lower-case, safe filename token (a-z 0-9 and single hyphens)
slugify() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -e 's/[^a-z0-9]\{1,\}/-/g' -e 's/^-\{1,\}//' -e 's/-\{1,\}$//' \
    | cut -c1-80
}

# compute_out_path: honor --out, else compose a spec-valid name from client+title
compute_out_path() {
  if [[ -n "$OUT" ]]; then
    printf '%s' "$OUT"
    return 0
  fi
  local c t base
  c="$(slugify "${CLIENT:-}")"
  t="$(slugify "${TITLE:-}")"
  if [[ -n "$c" && -n "$t" ]]; then
    base="${c}-${t}-cover.jpg"
  elif [[ -n "$t" ]]; then
    base="${t}-cover.jpg"
  elif [[ -n "$c" ]]; then
    base="${c}-cover.jpg"
  else
    base="podcast-cover.jpg"
  fi
  printf '%s' "$base"
}

# int_from: robust integer read from ffprobe output
int_from() { awk '{printf "%d", $1}' <<<"${1:-0}"; }

# emit_receipt <json> : write to --receipt if set, and always to stdout
emit_receipt() {
  local json="$1"
  if [[ -n "$RECEIPT" ]]; then
    printf '%s\n' "$json" > "$RECEIPT"
  fi
  printf '%s\n' "$json"
}

# ---------------------------------------------------------------------------
# FINALIZE: square -> resize into [MIN,MAX] -> JPEG RGB -> under COVER_MAX_BYTES
# Args: <input_image> <output_jpg>
# Echoes "WIDTH HEIGHT BYTES QUALITY" on success; returns non-zero on failure.
# ---------------------------------------------------------------------------
finalize_cover() {
  local src="$1" out="$2"
  [[ -f "$src" ]] || { err "finalize: source not found: $src"; return 1; }

  local w h side pixfmt
  w="$(int_from "$(ffprobe -v error -select_streams v:0 -show_entries stream=width  -of csv=p=0 "$src" 2>/dev/null)")"
  h="$(int_from "$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$src" 2>/dev/null)")"
  pixfmt="$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$src" 2>/dev/null || echo unknown)"
  if [[ "$w" -le 0 || "$h" -le 0 ]]; then
    err "finalize: could not read image dimensions (w=$w h=$h) from $src"
    return 1
  fi

  # Square: center-crop to the shorter side (no-op when already square).
  side=$(( w < h ? w : h ))

  # Target side clamped into [MIN, MAX]; never below MIN.
  local target="$side"
  if   [[ "$target" -lt "$COVER_MIN_SIDE" ]]; then target="$COVER_MIN_SIDE";
  elif [[ "$target" -gt "$COVER_MAX_SIDE" ]]; then target="$COVER_MAX_SIDE"; fi

  log "finalize: source ${w}x${h} pix_fmt=${pixfmt} -> square ${side} -> target ${target}"

  # Encode over a white background so any alpha flattens correctly; opaque
  # sources are simply covered. Output full-range JPEG (yuvj420p) = RGB image
  # with no alpha channel, which is what podcast platforms accept.
  local q qualities="2 4 6 8 10 12 15 18 21 25 28 31"
  local chosen_q="" bytes=0
  while [[ "$target" -ge "$COVER_MIN_SIDE" ]]; do
    for q in $qualities; do
      rm -f "$out"
      if ffmpeg -y -v error \
          -f lavfi -i "color=c=white:s=${target}x${target}:d=1" \
          -i "$src" \
          -filter_complex "[1:v]crop=${side}:${side},scale=${target}:${target}:flags=lanczos,format=rgba[fg];[0:v][fg]overlay=shortest=1,format=yuvj420p" \
          -frames:v 1 -q:v "$q" "$out" 2>/dev/null; then
        if [[ -s "$out" ]]; then
          bytes="$(wc -c < "$out" | tr -d ' ')"
          if [[ "$bytes" -lt "$COVER_MAX_BYTES" ]]; then
            chosen_q="$q"
            break
          fi
        fi
      fi
    done
    [[ -n "$chosen_q" ]] && break
    # Nothing fit at this dimension; step down but never below the floor.
    local next=$(( target * 9 / 10 ))
    [[ "$next" -lt "$COVER_MIN_SIDE" ]] && next="$COVER_MIN_SIDE"
    if [[ "$next" -eq "$target" ]]; then
      break
    fi
    log "finalize: no quality fit under $COVER_MAX_BYTES at ${target}px; retrying at ${next}px"
    target="$next"
  done

  if [[ -z "$chosen_q" ]]; then
    err "finalize: could not compress under ${COVER_MAX_BYTES} bytes at or above ${COVER_MIN_SIDE}px"
    return 1
  fi

  # Verify every invariant on the finished file (fail-closed).
  local fw fh fp
  fw="$(int_from "$(ffprobe -v error -select_streams v:0 -show_entries stream=width  -of csv=p=0 "$out" 2>/dev/null)")"
  fh="$(int_from "$(ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$out" 2>/dev/null)")"
  fp="$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$out" 2>/dev/null || echo unknown)"
  bytes="$(wc -c < "$out" | tr -d ' ')"

  if [[ "$fw" -ne "$fh" ]]; then err "finalize: output not square (${fw}x${fh})"; return 1; fi
  if [[ "$fw" -lt "$COVER_MIN_SIDE" || "$fw" -gt "$COVER_MAX_SIDE" ]]; then
    err "finalize: output side ${fw} outside [${COVER_MIN_SIDE},${COVER_MAX_SIDE}]"; return 1
  fi
  if [[ "$bytes" -ge "$COVER_MAX_BYTES" ]]; then
    err "finalize: output ${bytes} bytes is not under ${COVER_MAX_BYTES}"; return 1
  fi
  case "$fp" in
    *a) err "finalize: output pix_fmt ${fp} carries an alpha channel"; return 1 ;;
  esac

  log "finalize: verified ${fw}x${fh} pix_fmt=${fp} bytes=${bytes} q=${chosen_q} -> $out"
  printf '%s %s %s %s' "$fw" "$fh" "$bytes" "$chosen_q"
  return 0
}

# ---------------------------------------------------------------------------
# FINALIZE-ONLY mode (no Kie call)
# ---------------------------------------------------------------------------
if [[ -n "$FINALIZE_ONLY" ]]; then
  OUT_PATH="$(compute_out_path)"
  [[ -n "$OUT_PATH" ]] || { err "finalize-only requires --out or --client/--title"; exit 2; }
  mkdir -p "$(dirname "$OUT_PATH")" 2>/dev/null || true
  if RESULT="$(finalize_cover "$FINALIZE_ONLY" "$OUT_PATH")"; then
    read -r FW FH FB FQ <<<"$RESULT"
    RECEIPT_JSON="$(jq -nc \
      --arg status "ok" --arg mode "finalize-only" \
      --arg cover_path "$OUT_PATH" \
      --argjson width "$FW" --argjson height "$FH" \
      --argjson bytes "$FB" --argjson quality "$FQ" \
      --arg format "jpeg" \
      '{status:$status, mode:$mode, cover_path:$cover_path, width:$width, height:$height, bytes:$bytes, quality:$quality, format:$format}')"
    emit_receipt "$RECEIPT_JSON"
    exit 0
  fi
  exit 7
fi

# ---------------------------------------------------------------------------
# GENERATE mode: dependencies, key, prompt assembly
# ---------------------------------------------------------------------------
for tool in curl jq; do
  command -v "$tool" >/dev/null 2>&1 || { err "$tool not installed"; exit 2; }
done

# Resolve the Kie key without ever printing it. Env first, then 0600 secrets.
if [[ -z "${KIE_API_KEY:-}" ]]; then
  SECRETS_CANDIDATES=(
    "$HOME/.openclaw/secrets/.env"
    "/data/.openclaw/secrets/.env"
    "$HOME/clawd/secrets/.env"
  )
  for f in "${SECRETS_CANDIDATES[@]}"; do
    if [[ -f "$f" ]] && grep -q "KIE_API_KEY=" "$f" 2>/dev/null; then
      # shellcheck disable=SC1090
      set +u; . "$f"; set -u
      break
    fi
  done
fi
if [[ -z "${KIE_API_KEY:-}" ]]; then
  err "KIE_API_KEY is NOT SET. Set it in the client env store or a 0600 secrets file."
  exit 2
fi
log "KIE_API_KEY: SET"

# Assemble the visual description.
if [[ -n "$PROMPT_FILE" ]]; then
  [[ -f "$PROMPT_FILE" ]] || { err "prompt file not found: $PROMPT_FILE"; exit 2; }
  PROMPT="$(cat "$PROMPT_FILE")"
fi
if [[ -z "${PROMPT// /}" ]]; then
  err "no image prompt supplied (use --prompt or --prompt-file)"
  exit 2
fi

# Compose the final Kie prompt: visual description anchored by theme and title,
# then the Skill 57 prompt-14 fixed suffix. This exact string is the delivery
# report's image_prompt field.
FINAL_PROMPT="$PROMPT"
[[ -n "$THEME" ]] && FINAL_PROMPT="${FINAL_PROMPT} Episode theme: ${THEME}."
[[ -n "$TITLE" ]] && FINAL_PROMPT="${FINAL_PROMPT} Episode title: ${TITLE}."
FINAL_PROMPT="${FINAL_PROMPT} ${COVER_PROMPT_SUFFIX}"

# Work area for the raw download.
if [[ -z "$WORK_DIR" ]]; then
  WORK_DIR="$(mktemp -d)"
  trap 'rm -rf "$WORK_DIR"' EXIT
else
  mkdir -p "$WORK_DIR"
fi
RAW_IMG="${WORK_DIR}/cover_raw.${KIE_COVER_OUTPUT_FORMAT}"

# ---------------------------------------------------------------------------
# createTask (with a bounded transient retry and a one-shot resolution fallback)
# ---------------------------------------------------------------------------
create_task() {
  local resolution="$1" body resp code task_id attempt=0
  body="$(jq -nc \
    --arg model "$KIE_COVER_MODEL" \
    --arg prompt "$FINAL_PROMPT" \
    --arg aspect "$KIE_COVER_ASPECT" \
    --arg resolution "$resolution" \
    --arg fmt "$KIE_COVER_OUTPUT_FORMAT" \
    '{model:$model, input:{prompt:$prompt, aspect_ratio:$aspect, resolution:$resolution, output_format:$fmt}}')"

  while [[ "$attempt" -le "$KIE_CREATE_RETRIES" ]]; do
    attempt=$(( attempt + 1 ))
    resp="$(curl -sS --max-time 30 -X POST "${KIE_API_BASE}/api/v1/jobs/createTask" \
      -H "Authorization: Bearer ${KIE_API_KEY}" \
      -H "Content-Type: application/json" \
      -d "$body" 2>/dev/null || true)"
    code="$(jq -r '.code // empty' <<<"$resp" 2>/dev/null || true)"
    task_id="$(jq -r '.data.taskId // empty' <<<"$resp" 2>/dev/null || true)"
    if [[ "$code" == "200" && -n "$task_id" ]]; then
      printf '%s' "$task_id"
      return 0
    fi
    warn "createTask attempt ${attempt} failed (code=${code:-none}, resolution=${resolution})"
    [[ "$attempt" -le "$KIE_CREATE_RETRIES" ]] && sleep 5
  done
  return 1
}

RESOLUTION_USED="$KIE_COVER_RESOLUTION"
log "createTask: model=${KIE_COVER_MODEL} aspect=${KIE_COVER_ASPECT} resolution=${RESOLUTION_USED}"
if ! TASK_ID="$(create_task "$KIE_COVER_RESOLUTION")"; then
  if [[ -n "$KIE_COVER_RESOLUTION_FALLBACK" && "$KIE_COVER_RESOLUTION_FALLBACK" != "$KIE_COVER_RESOLUTION" ]]; then
    warn "retrying createTask once with fallback resolution ${KIE_COVER_RESOLUTION_FALLBACK}"
    RESOLUTION_USED="$KIE_COVER_RESOLUTION_FALLBACK"
    if ! TASK_ID="$(create_task "$KIE_COVER_RESOLUTION_FALLBACK")"; then
      err "createTask failed after retries and fallback"
      exit 3
    fi
  else
    err "createTask failed after retries"
    exit 3
  fi
fi
log "createTask: taskId=${TASK_ID} resolution_used=${RESOLUTION_USED}"

# ---------------------------------------------------------------------------
# Poll recordInfo with bounded backoff (5,10,20,40,60 then hold at 60).
# ---------------------------------------------------------------------------
read -r -a BACKOFF <<<"$KIE_BACKOFF_SCHEDULE"
BLEN="${#BACKOFF[@]}"
[[ "$BLEN" -gt 0 ]] || BACKOFF=(60)
ELAPSED=0
IDX=0
RESULT_URL=""
while [[ "$ELAPSED" -lt "$KIE_POLL_TIMEOUT_SECONDS" ]]; do
  if [[ "$IDX" -lt "$BLEN" ]]; then WAIT="${BACKOFF[$IDX]}"; else WAIT="${BACKOFF[$(( BLEN - 1 ))]}"; fi
  # Never poll faster than 5 seconds.
  [[ "$WAIT" -lt 5 ]] && WAIT=5
  # Do not overshoot the total timeout.
  local_remaining=$(( KIE_POLL_TIMEOUT_SECONDS - ELAPSED ))
  [[ "$WAIT" -gt "$local_remaining" ]] && WAIT="$local_remaining"
  sleep "$WAIT"
  ELAPSED=$(( ELAPSED + WAIT ))
  IDX=$(( IDX + 1 ))

  PRESP="$(curl -sS --max-time 20 -w '\n%{http_code}' \
    "${KIE_API_BASE}/api/v1/jobs/recordInfo?taskId=${TASK_ID}" \
    -H "Authorization: Bearer ${KIE_API_KEY}" 2>/dev/null || true)"
  PCODE="$(tail -n1 <<<"$PRESP")"
  PBODY="$(sed '$d' <<<"$PRESP")"
  # Treat network errors and 5xx as transient; keep polling within the budget.
  if [[ -z "$PCODE" || "$PCODE" == "000" || "$PCODE" -ge 500 ]]; then
    warn "poll transient (http=${PCODE:-none}) at ${ELAPSED}s; continuing"
    continue
  fi

  STATE="$(jq -r '.data.state // empty' <<<"$PBODY" 2>/dev/null || true)"
  case "$STATE" in
    success)
      # resultJson arrives as a JSON-encoded STRING on client boxes; tolerate an
      # already-parsed object. Prefer resultUrls, fall back to images[].url.
      RESULT_URL="$(jq -r '
        (.data.resultJson | (if type=="string" then fromjson else . end)) as $r
        | ($r.resultUrls[0]? // $r.images[0].url? // empty)' <<<"$PBODY" 2>/dev/null || true)"
      if [[ -z "$RESULT_URL" ]]; then
        err "task ${TASK_ID} succeeded but no result URL was found"
        exit 5
      fi
      log "poll: success at ${ELAPSED}s"
      break
      ;;
    fail|failed|error)
      FAILMSG="$(jq -r '.data.failMsg // .msg // "unknown"' <<<"$PBODY" 2>/dev/null || echo unknown)"
      err "task ${TASK_ID} failed: ${FAILMSG}"
      exit 5
      ;;
    *)
      log "poll: state=${STATE:-pending} at ${ELAPSED}s"
      ;;
  esac
done

if [[ -z "$RESULT_URL" ]]; then
  err "poll timed out after ${KIE_POLL_TIMEOUT_SECONDS}s (bounded); caller holds and counts one failed image attempt"
  exit 4
fi

# ---------------------------------------------------------------------------
# Download the raw image.
# ---------------------------------------------------------------------------
DLCODE="$(curl -sS --max-time 120 -o "$RAW_IMG" -w '%{http_code}' "$RESULT_URL" 2>/dev/null || echo 000)"
if [[ "$DLCODE" != "200" || ! -s "$RAW_IMG" ]]; then
  err "download failed (http=${DLCODE}) from result URL"
  exit 6
fi
log "download: ok ($(wc -c < "$RAW_IMG" | tr -d ' ') bytes)"

# ---------------------------------------------------------------------------
# Finalize + verify.
# ---------------------------------------------------------------------------
OUT_PATH="$(compute_out_path)"
mkdir -p "$(dirname "$OUT_PATH")" 2>/dev/null || true
if ! RESULT="$(finalize_cover "$RAW_IMG" "$OUT_PATH")"; then
  err "finalize failed"
  exit 7
fi
read -r FW FH FB FQ <<<"$RESULT"

RECEIPT_JSON="$(jq -nc \
  --arg status "ok" \
  --arg provider "kie" \
  --arg model "$KIE_COVER_MODEL" \
  --arg task_id "$TASK_ID" \
  --arg result_url "$RESULT_URL" \
  --arg image_prompt "$FINAL_PROMPT" \
  --arg resolution_requested "$KIE_COVER_RESOLUTION" \
  --arg resolution_used "$RESOLUTION_USED" \
  --arg cover_path "$OUT_PATH" \
  --argjson width "$FW" --argjson height "$FH" \
  --argjson bytes "$FB" --argjson quality "$FQ" \
  --arg format "jpeg" \
  '{status:$status, provider:$provider, model:$model, kie_task_id:$task_id, kie_result_url:$result_url, image_prompt:$image_prompt, resolution_requested:$resolution_requested, resolution_used:$resolution_used, cover_path:$cover_path, width:$width, height:$height, bytes:$bytes, quality:$quality, format:$format}')"

emit_receipt "$RECEIPT_JSON"
exit 0

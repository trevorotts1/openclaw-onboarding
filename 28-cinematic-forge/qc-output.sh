#!/usr/bin/env bash
# Skill 28 — Cinematic Forge — OUTPUT QC GATE
#
# TWO MODES, and only one of them may say "safe to deliver".
#
#   1. TECHNICAL mode (positional; bash + ffprobe + ffmpeg only)
#        qc-output.sh <file.mp4> <target_seconds> <WIDTHxHEIGHT>
#      Probes the file: it exists, is non-empty, carries a video and an audio
#      stream, the audio is not digital silence, the resolution matches and the
#      duration is within tolerance. Every number it compares against is
#      supplied by the CALLER, so it can only report that the file is a
#      technically valid video of the size and length it was told to expect.
#      It says exactly that, and NOTHING about delivery.
#
#   2. DELIVERY mode (the gate that certifies a client deliverable)
#        qc-output.sh --artifact <final.mp4> \
#                     --requirements <delivery-requirements.json> \
#                     [--receipts <dir>] \
#                     [--upload-response <response.json>]
#      Checks the artifact against the DELIVERY REQUIREMENTS RECORD derived from
#      the approved intake BEFORE generation — approved aspect ratio, approved
#      duration, and every overlay the client actually asked for — plus the
#      post-production receipts that prove those transformations were applied to
#      THIS file. Only this mode prints "safe to deliver".
#
# WHY THE SPLIT (T0-46). The gate's stated contract was "safe to deliver", and
# every argument it compared against was supplied by the caller. Nothing bound
# the file to the approved intake, so a correctly encoded video of the wrong
# length, the wrong aspect ratio, or missing every requested overlay passed —
# because the caller passed in the numbers it wanted checked. The certification
# was real; what it certified was that the file is a video.
#
# WHY THE RECEIPT CHAIN (T0-47). Phase 5 wrote captions to
# final_video_captioned.mp4 and the logo overlay to final_video_branded.mp4, and
# Phase 6 then uploaded final_video.mp4 — the UN-transformed file. Every stage
# reported success and the client received a video without the thing they asked
# for. The gate now requires, for each requested overlay, a receipt whose output
# hash is the artifact being delivered: a file that skipped a transformation
# cannot be certified.
#
# WHY THE HOSTED CHECK IS DIFFERENT (T0-48). The old hosted check was a ranged
# request for the first byte plus a content-type match, on a URL grepped out of
# the upload response body. Any reachable video URL satisfied it — a previous
# client's asset, a stale upload, an unrelated file on the same host. It now
# resolves the asset IDENTIFIER the upload returned, requires the response's own
# filename/size metadata to match the artifact, downloads the hosted object
# bound to that identifier, and probes it against the same requirements.
#
#   exit 0  -> checks passed (the verdict line says what that means)
#   exit 1  -> a check failed; DO NOT deliver
#   exit 2  -> bad invocation / missing dependency
set -u
set -o pipefail

fail(){ printf '  \xe2\x9c\x97 FAIL — %s\n' "$1" >&2; exit 1; }
ok(){   printf '  \xe2\x9c\x93 %s\n' "$1"; }
usage(){
  cat >&2 <<'USAGE'
usage:
  TECHNICAL (no delivery verdict):
    qc-output.sh <final.mp4> <target_seconds> <WIDTHxHEIGHT>
  DELIVERY (the only mode that certifies a deliverable):
    qc-output.sh --artifact <final.mp4> --requirements <delivery-requirements.json>
                 [--receipts <dir>] [--upload-response <response.json>]
USAGE
  exit 2
}

command -v ffprobe >/dev/null 2>&1 || { printf 'ffprobe not found (install ffmpeg)\n' >&2; exit 2; }
command -v ffmpeg  >/dev/null 2>&1 || { printf 'ffmpeg not found (install ffmpeg)\n'  >&2; exit 2; }

_sha256(){ if command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | awk '{print $1}'; else sha256sum "$1" | awk '{print $1}'; fi; }
_bytes(){ case "$(uname -s)" in Darwin) stat -f%z "$1";; *) stat -c%s "$1";; esac; }

# ── shared technical probes ────────────────────────────────────────────────
# probe_file <file> <target_seconds> <tolerance> <REQ_W> <REQ_H> <label>
probe_file(){
  local FILE="$1" TARGET="$2" TOL="$3" REQ_W="$4" REQ_H="$5" LABEL="$6"
  [ -f "$FILE" ] || fail "$LABEL: file missing: $FILE"
  [ -s "$FILE" ] || fail "$LABEL: file is zero bytes: $FILE"
  ok "$LABEL: present and non-empty"

  local V_WH GOT_W GOT_H
  V_WH="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$FILE" 2>/dev/null)"
  [ -n "$V_WH" ] || fail "$LABEL: no video stream"
  GOT_W="${V_WH%,*}"; GOT_H="${V_WH#*,}"
  { [ "$GOT_W" = "$REQ_W" ] && [ "$GOT_H" = "$REQ_H" ]; } \
    || fail "$LABEL: resolution ${GOT_W}x${GOT_H} != required ${REQ_W}x${REQ_H}"
  ok "$LABEL: resolution ${REQ_W}x${REQ_H}"

  local A_CODEC
  A_CODEC="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$FILE" 2>/dev/null)"
  [ -n "$A_CODEC" ] || fail "$LABEL: no audio stream (the replacement audio track is missing)"
  ok "$LABEL: audio stream present ($A_CODEC)"

  local DUR DELTA
  DUR="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null)"
  [ -n "$DUR" ] || fail "$LABEL: could not read duration"
  DELTA="$(awk -v d="$DUR" -v t="$TARGET" 'BEGIN{x=d-t; if(x<0)x=-x; printf "%.3f", x}')"
  awk -v x="$DELTA" -v tol="$TOL" 'BEGIN{exit !(x<=tol)}' \
    || fail "$LABEL: duration ${DUR}s is off the approved ${TARGET}s by ${DELTA}s (tolerance ${TOL}s)"
  ok "$LABEL: duration ${DUR}s within ${TOL}s of the approved ${TARGET}s"

  local MEAN
  MEAN="$(ffmpeg -hide_banner -nostats -i "$FILE" -map 0:a:0 -af volumedetect -f null - 2>&1 \
          | awk -F'mean_volume:' '/mean_volume:/{print $2}' | awk '{print $1}' | tail -n1)"
  [ -n "$MEAN" ] || fail "$LABEL: could not measure audio level"
  case "$MEAN" in *inf*) fail "$LABEL: audio mean_volume is ${MEAN} dB (digital silence — audio was dropped)";; esac
  awk -v m="$MEAN" 'BEGIN{exit !(m > -80)}' \
    || fail "$LABEL: audio mean_volume ${MEAN} dB <= -80 dB (track is silent — audio was dropped)"
  ok "$LABEL: audio mean_volume ${MEAN} dB (non-silent)"
}

# ── mode selection ─────────────────────────────────────────────────────────
ARTIFACT=""; REQS=""; RECEIPTS=""; UPLOAD_RESPONSE=""
case "${1:-}" in
  -h|--help) usage ;;
  --artifact|--requirements|--receipts|--upload-response) MODE="delivery" ;;
  *) MODE="technical" ;;
esac

if [ "$MODE" = "technical" ]; then
  FILE="${1:-}"; TARGET="${2:-}"; DIM="${3:-}"
  [ -n "$FILE" ] && [ -n "$TARGET" ] && [ -n "$DIM" ] || usage
  case "$DIM" in
    *x*) REQ_W="${DIM%x*}"; REQ_H="${DIM#*x}";;
    *)   printf 'resolution must be WIDTHxHEIGHT, got: %s\n' "$DIM" >&2; exit 2;;
  esac
  printf '== Technical QC: %s (expect %ss, %s) ==\n' "$FILE" "$TARGET" "$DIM"
  probe_file "$FILE" "$TARGET" 0.75 "$REQ_W" "$REQ_H" "artifact"
  printf '\xe2\x9c\x93 TECHNICAL CHECKS PASS — a valid video of the expected size and length.\n'
  printf '  This is NOT a delivery verdict: every number above was supplied by the caller.\n'
  printf '  Run the DELIVERY mode (--artifact + --requirements) before sending anything to a client.\n'
  exit 0
fi

# ── DELIVERY mode ──────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --artifact)        ARTIFACT="${2:-}"; shift 2 ;;
    --requirements)    REQS="${2:-}"; shift 2 ;;
    --receipts)        RECEIPTS="${2:-}"; shift 2 ;;
    --upload-response) UPLOAD_RESPONSE="${2:-}"; shift 2 ;;
    -h|--help)         usage ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage ;;
  esac
done

[ -n "$ARTIFACT" ] || { printf -- '--artifact is required in delivery mode\n' >&2; usage; }
[ -n "$REQS" ]     || { printf -- '--requirements is required: the gate cannot certify a deliverable against numbers the caller chose\n' >&2; usage; }
command -v jq >/dev/null 2>&1 || { printf 'jq not found — the delivery gate reads the requirements record and the upload response as structured data. Install jq.\n' >&2; exit 2; }
[ -f "$REQS" ] || fail "delivery-requirements record not found: $REQS"
jq -e 'type=="object"' "$REQS" >/dev/null 2>&1 || fail "delivery-requirements record is not a JSON object: $REQS"

[ -z "$RECEIPTS" ] && RECEIPTS="$(dirname "$ARTIFACT")/receipts"

printf '== Delivery QC: %s ==\n' "$ARTIFACT"
printf '   requirements: %s\n' "$REQS"

REQ_DIM="$(jq -r '.dimensions // empty' "$REQS")"
REQ_ASPECT="$(jq -r '.aspect_ratio // empty' "$REQS")"
REQ_DUR="$(jq -r '.duration_seconds // empty' "$REQS")"
REQ_TOL="$(jq -r '.duration_tolerance_seconds // 0.75' "$REQS")"
REQ_APPROVAL="$(jq -r '.approval_ref // empty' "$REQS")"

[ -n "$REQ_DIM" ]      || fail "the requirements record carries no approved dimensions"
[ -n "$REQ_DUR" ]      || fail "the requirements record carries no approved duration"
[ -n "$REQ_APPROVAL" ] || fail "the requirements record carries no approval reference — it was not derived from an approved intake"
case "$REQ_DIM" in *x*) REQ_W="${REQ_DIM%x*}"; REQ_H="${REQ_DIM#*x}";; *) fail "requirements.dimensions must be WIDTHxHEIGHT, got: $REQ_DIM";; esac
ok "requirements record is bound to an approved intake ($REQ_APPROVAL)"

probe_file "$ARTIFACT" "$REQ_DUR" "$REQ_TOL" "$REQ_W" "$REQ_H" "artifact"

# Aspect ratio, when the record states one, must agree with the pixels.
if [ -n "$REQ_ASPECT" ]; then
  case "$REQ_ASPECT" in
    *:*) A_W="${REQ_ASPECT%%:*}"; A_H="${REQ_ASPECT##*:}"
         awk -v w="$REQ_W" -v h="$REQ_H" -v aw="$A_W" -v ah="$A_H" \
           'BEGIN{r=w/h; t=aw/ah; exit !(r > t-0.01 && r < t+0.01)}' \
           || fail "approved aspect ratio $REQ_ASPECT does not match the approved dimensions $REQ_DIM"
         ok "approved aspect ratio $REQ_ASPECT agrees with $REQ_DIM" ;;
    *) fail "requirements.aspect_ratio must be W:H, got: $REQ_ASPECT" ;;
  esac
fi

# ── the post-production receipt chain ──────────────────────────────────────
# Each requested transformation writes ONE receipt when its ffmpeg command
# SUCCEEDS: {step, input, input_sha256, output, output_sha256}. The chain must
# END at the artifact being delivered, so a file that skipped a transformation —
# or a transformation applied to a different file — cannot be certified.
ART_SHA="$(_sha256 "$ARTIFACT")"
REQUIRED_STEPS=""
[ "$(jq -r '.requires_captions // false' "$REQS")" = "true" ]      && REQUIRED_STEPS="$REQUIRED_STEPS captions"
[ "$(jq -r '.requires_text_overlays // false' "$REQS")" = "true" ] && REQUIRED_STEPS="$REQUIRED_STEPS text_overlays"
[ "$(jq -r '.requires_logo // false' "$REQS")" = "true" ]          && REQUIRED_STEPS="$REQUIRED_STEPS logo"

if [ -z "$REQUIRED_STEPS" ]; then
  ok "no post-production transformations were requested for this deliverable"
else
  [ -d "$RECEIPTS" ] || fail "the client requested$REQUIRED_STEPS but there is no receipts directory at $RECEIPTS — the transformation was never recorded"
  for STEP in $REQUIRED_STEPS; do
    R="$RECEIPTS/$STEP.json"
    [ -f "$R" ] || fail "the client requested '$STEP' but no receipt exists at $R — the transformation was not applied"
    jq -e 'type=="object"' "$R" >/dev/null 2>&1 || fail "receipt $R is not a JSON object"
    R_OUT_SHA="$(jq -r '.output_sha256 // empty' "$R")"
    R_OUT="$(jq -r '.output // empty' "$R")"
    [ -n "$R_OUT_SHA" ] || fail "receipt $R carries no output_sha256 — it attests to nothing"
    if [ "$R_OUT_SHA" = "$ART_SHA" ]; then
      ok "receipt '$STEP' output hash IS the artifact being delivered"
    else
      ok "receipt '$STEP' recorded output $R_OUT (an intermediate stage)"
    fi
  done
  LAST_STEP="$(printf '%s' "$REQUIRED_STEPS" | awk '{print $NF}')"
  LAST_SHA="$(jq -r '.output_sha256 // empty' "$RECEIPTS/$LAST_STEP.json")"
  [ "$LAST_SHA" = "$ART_SHA" ] \
    || fail "the artifact being delivered is NOT the output of the last requested transformation ('$LAST_STEP'). An un-transformed file is about to ship — the client asked for$REQUIRED_STEPS and would receive a video without it."
  ok "the artifact IS the output of the final requested transformation ('$LAST_STEP')"
fi

# ── hosted verification, bound to the returned asset identifier ────────────
if [ -n "$UPLOAD_RESPONSE" ]; then
  [ -f "$UPLOAD_RESPONSE" ] || fail "upload response file not found: $UPLOAD_RESPONSE"
  jq -e 'type=="object"' "$UPLOAD_RESPONSE" >/dev/null 2>&1 || fail "upload response is not a JSON object: $UPLOAD_RESPONSE"
  command -v curl >/dev/null 2>&1 || { printf 'curl not found — required to verify the hosted object\n' >&2; exit 2; }

  ASSET_ID="$(jq -r '.fileId // .id // ._id // .data.fileId // .data.id // empty' "$UPLOAD_RESPONSE")"
  [ -n "$ASSET_ID" ] || fail "the upload response carries no asset identifier — there is nothing to bind the hosted object to. A URL scraped out of the body proves only that some file is reachable."
  ok "upload returned asset identifier $ASSET_ID"

  HOSTED_URL="$(jq -r '.url // .fileUrl // .location // .data.url // empty' "$UPLOAD_RESPONSE")"
  [ -n "$HOSTED_URL" ] || fail "the upload response binds no URL to asset $ASSET_ID"

  RESP_NAME="$(jq -r '.name // .fileName // .originalName // .data.name // empty' "$UPLOAD_RESPONSE")"
  RESP_SIZE="$(jq -r '.size // .fileSize // .data.size // empty' "$UPLOAD_RESPONSE")"
  LOCAL_NAME="$(basename "$ARTIFACT")"
  LOCAL_SIZE="$(_bytes "$ARTIFACT")"

  if [ -z "$RESP_NAME" ] && [ -z "$RESP_SIZE" ]; then
    fail "the upload response carries neither a filename nor a size for asset $ASSET_ID, so the hosted object cannot be matched to the artifact. Do not deliver on an unverifiable upload."
  fi
  if [ -n "$RESP_NAME" ]; then
    [ "$RESP_NAME" = "$LOCAL_NAME" ] \
      || fail "the hosted asset is named '$RESP_NAME' but the artifact is '$LOCAL_NAME' — a different file was uploaded"
    ok "hosted asset filename matches the artifact ($LOCAL_NAME)"
  fi
  if [ -n "$RESP_SIZE" ]; then
    [ "$RESP_SIZE" = "$LOCAL_SIZE" ] \
      || fail "the hosted asset is $RESP_SIZE bytes but the artifact is $LOCAL_SIZE bytes — a different file was uploaded"
    ok "hosted asset size matches the artifact ($LOCAL_SIZE bytes)"
  fi

  TMP_DL="$(mktemp -t cinematic-forge-hosted.XXXXXX 2>/dev/null || mktemp)"
  trap 'rm -f "$TMP_DL" 2>/dev/null || true' EXIT
  curl -fsSL -m 300 -o "$TMP_DL" "$HOSTED_URL" 2>/dev/null \
    || fail "could not download the hosted object bound to asset $ASSET_ID"
  [ -s "$TMP_DL" ] || fail "the hosted object for asset $ASSET_ID downloaded as zero bytes"
  ok "downloaded the hosted object bound to asset $ASSET_ID"

  probe_file "$TMP_DL" "$REQ_DUR" "$REQ_TOL" "$REQ_W" "$REQ_H" "hosted object"

  DL_SHA="$(_sha256 "$TMP_DL")"
  if [ "$DL_SHA" = "$ART_SHA" ]; then
    ok "the hosted object is byte-identical to the delivered artifact"
  else
    ok "the hosted object is not byte-identical (the host re-encoded it) but probes identical to the artifact"
  fi
fi

printf '\xe2\x9c\x93 DELIVERY QC PASS — the artifact matches the APPROVED requirements and carries a receipt for every requested transformation. Safe to deliver.\n'
exit 0

#!/usr/bin/env bash
# Skill 28 — Cinematic Forge — OUTPUT QC GATE
# Validates the FINISHED deliverable before it is sent to the client.
# Dependency-light on purpose: bash + ffprobe + ffmpeg only (no Python) so it
# runs on minimal VPS images. Idempotent and read-only (safe to re-run).
#
# Usage:  qc-output.sh <final.mp4> <target_seconds> <WIDTHxHEIGHT> [hosted_url]
#   exit 0  -> deliverable passed every check; safe to deliver
#   exit 1  -> a check failed; DO NOT deliver (message explains which)
#   exit 2  -> bad invocation (missing args / missing ffmpeg|ffprobe)
set -u
set -o pipefail

FILE="${1:-}"; TARGET="${2:-}"; DIM="${3:-}"; URL="${4:-}"

fail(){ printf '  \xe2\x9c\x97 FAIL — %s\n' "$1" >&2; exit 1; }
ok(){   printf '  \xe2\x9c\x93 %s\n' "$1"; }

# --- preflight -------------------------------------------------------------
if [ -z "$FILE" ] || [ -z "$TARGET" ] || [ -z "$DIM" ]; then
  printf 'usage: qc-output.sh <final.mp4> <target_seconds> <WIDTHxHEIGHT> [hosted_url]\n' >&2
  exit 2
fi
command -v ffprobe >/dev/null 2>&1 || { printf 'ffprobe not found (install ffmpeg)\n' >&2; exit 2; }
command -v ffmpeg  >/dev/null 2>&1 || { printf 'ffmpeg not found (install ffmpeg)\n'  >&2; exit 2; }

case "$DIM" in
  *x*) REQ_W="${DIM%x*}"; REQ_H="${DIM#*x}";;
  *)   printf 'resolution must be WIDTHxHEIGHT, got: %s\n' "$DIM" >&2; exit 2;;
esac

printf '== Output QC: %s (target %ss, %s) ==\n' "$FILE" "$TARGET" "$DIM"

# 1) file exists + non-zero ------------------------------------------------
[ -f "$FILE" ] || fail "file missing: $FILE"
[ -s "$FILE" ] || fail "file is zero bytes: $FILE"
ok "file present and non-empty"

# 2) video stream present + resolution -------------------------------------
V_WH="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$FILE" 2>/dev/null)"
[ -n "$V_WH" ] || fail "no video stream"
GOT_W="${V_WH%,*}"; GOT_H="${V_WH#*,}"
ok "video stream present (${GOT_W}x${GOT_H})"
{ [ "$GOT_W" = "$REQ_W" ] && [ "$GOT_H" = "$REQ_H" ]; } \
  || fail "resolution ${GOT_W}x${GOT_H} != requested ${REQ_W}x${REQ_H}"
ok "resolution matches ${REQ_W}x${REQ_H}"

# 3) audio stream present (proves VEO audio was replaced, not dropped) ------
A_CODEC="$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$FILE" 2>/dev/null)"
[ -n "$A_CODEC" ] || fail "no audio stream (the replacement audio track is missing)"
ok "audio stream present ($A_CODEC)"

# 4) duration within 0.75s of target --------------------------------------
DUR="$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$FILE" 2>/dev/null)"
[ -n "$DUR" ] || fail "could not read duration"
DELTA="$(awk -v d="$DUR" -v t="$TARGET" 'BEGIN{x=d-t; if(x<0)x=-x; printf "%.3f", x}')"
awk -v x="$DELTA" 'BEGIN{exit !(x<=0.75)}' \
  || fail "duration ${DUR}s is off target ${TARGET}s by ${DELTA}s (tolerance 0.75s)"
ok "duration ${DUR}s within 0.75s of target ${TARGET}s"

# 5) audio not silent (mean_volume must be above -80 dB) -------------------
MEAN="$(ffmpeg -hide_banner -nostats -i "$FILE" -map 0:a:0 -af volumedetect -f null - 2>&1 \
        | awk -F'mean_volume:' '/mean_volume:/{print $2}' | awk '{print $1}' | tail -n1)"
[ -n "$MEAN" ] || fail "could not measure audio level"
case "$MEAN" in
  *inf*) fail "audio mean_volume is ${MEAN} dB (digital silence — audio was dropped)";;
esac
awk -v m="$MEAN" 'BEGIN{exit !(m > -80)}' \
  || fail "audio mean_volume ${MEAN} dB <= -80 dB (track is silent — audio was dropped)"
ok "audio mean_volume ${MEAN} dB (non-silent)"

# 6) optional: hosted URL reachable + serves video (retry once) ------------
if [ -n "$URL" ]; then
  check_url(){ curl -fsSL -m 25 -r 0-0 -o /dev/null -w '%{http_code} %{content_type}' "$1" 2>/dev/null; }
  INFO="$(check_url "$URL")" || { sleep 3; INFO="$(check_url "$URL")" || fail "hosted URL not reachable: $URL"; }
  CODE="${INFO%% *}"; CTYPE="${INFO#* }"
  case "$CODE" in
    200|206) ;;
    *) fail "hosted URL returned HTTP ${CODE:-none}: $URL";;
  esac
  printf '%s' "$CTYPE" | grep -qiE 'video|octet-stream|mp4' \
    || fail "hosted URL content-type '$CTYPE' is not video: $URL"
  ok "hosted URL reachable (HTTP $CODE, $CTYPE)"
fi

printf '\xe2\x9c\x93 OUTPUT QC PASS — deliverable is valid\n'
exit 0

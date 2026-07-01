#!/usr/bin/env bash
# merge_reel.sh — Skill 35 video merge helper
# Implements the full normalize → merge → VO-overlay → QC pipeline
# described in references/playbook.md Section 16.
#
# Usage:
#   bash merge_reel.sh <clips_list.txt> <voiceover.mp3> <output.mp4> [crossfade|cut] [target_min_s] [target_max_s]
#
# Arguments:
#   clips_list.txt  — path to a text file listing raw (un-normalized) clip paths,
#                     one per line (plain paths, NOT the ffmpeg concat "file '...'" format).
#   voiceover.mp3   — path to the continuous voiceover audio file.
#   output.mp4      — path for the final assembled Reel.
#   crossfade|cut   — (optional) merge style; default: cut
#   target_min_s    — (optional) minimum acceptable duration in seconds; default: 55
#   target_max_s    — (optional) maximum acceptable duration in seconds; default: 62
#
# Exits 0 on success with final_reel.mp4 ready to upload.
# Exits 1 on any failure; prints a clear error message.
#
# Requirements: ffmpeg >= 4.0, ffprobe (bundled with ffmpeg), bash >= 3.2

set -euo pipefail

CLIPS_LIST="${1:-}"
VO_FILE="${2:-}"
OUTPUT="${3:-final_reel.mp4}"
MERGE_STYLE="${4:-cut}"
TARGET_MIN="${5:-55}"
TARGET_MAX="${6:-62}"
XFADE_DUR="0.5"

# --- Validate inputs ---
if [[ -z "$CLIPS_LIST" || -z "$VO_FILE" ]]; then
  echo "ERROR: Usage: bash merge_reel.sh <clips_list.txt> <voiceover.mp3> <output.mp4> [crossfade|cut]"
  exit 1
fi

if [[ ! -f "$CLIPS_LIST" ]]; then
  echo "ERROR: clips list file not found: $CLIPS_LIST"
  exit 1
fi

if [[ ! -f "$VO_FILE" ]]; then
  echo "ERROR: voiceover file not found: $VO_FILE"
  exit 1
fi

command -v ffmpeg  >/dev/null 2>&1 || { echo "ERROR: ffmpeg not installed"; exit 1; }
command -v ffprobe >/dev/null 2>&1 || { echo "ERROR: ffprobe not installed (install ffmpeg)"; exit 1; }

# --- Setup temp dir ---
TMPDIR_LOCAL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_LOCAL"' EXIT

echo "[merge_reel] Temp dir: $TMPDIR_LOCAL"
echo "[merge_reel] Merge style: $MERGE_STYLE"

# --- Step D: Normalize every clip ---
NORM_LIST="$TMPDIR_LOCAL/norm_list.txt"
> "$NORM_LIST"

IDX=0
while IFS= read -r RAW_CLIP || [[ -n "$RAW_CLIP" ]]; do
  [[ -z "$RAW_CLIP" ]] && continue
  IDX=$((IDX + 1))
  NORM_OUT="$TMPDIR_LOCAL/norm_$(printf '%02d' $IDX).mp4"
  echo "[merge_reel] Normalizing clip $IDX: $RAW_CLIP -> $NORM_OUT"
  ffmpeg -y -i "$RAW_CLIP" \
    -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,fps=30,setsar=1" \
    -c:v libx264 -pix_fmt yuv420p \
    -c:a aac -ar 48000 \
    "$NORM_OUT" 2>&1 | tail -3
  echo "file '$NORM_OUT'" >> "$NORM_LIST"
done < "$CLIPS_LIST"

if [[ $IDX -eq 0 ]]; then
  echo "ERROR: no clips found in $CLIPS_LIST"
  exit 1
fi

echo "[merge_reel] Normalized $IDX clips."

MERGED="$TMPDIR_LOCAL/merged.mp4"

# --- Step E: Merge ---
if [[ "$MERGE_STYLE" == "crossfade" ]]; then
  echo "[merge_reel] Merging with crossfade transitions..."
  # Build xfade filter chain dynamically
  INPUTS=()
  while IFS= read -r LINE; do
    PATH_VAL="${LINE#file \'}"
    PATH_VAL="${PATH_VAL%\'}"
    INPUTS+=("$PATH_VAL")
  done < "$NORM_LIST"

  N=${#INPUTS[@]}
  if [[ $N -eq 1 ]]; then
    cp "${INPUTS[0]}" "$MERGED"
  else
    # Build ffmpeg input args and filter_complex
    FF_ARGS=()
    for f in "${INPUTS[@]}"; do
      FF_ARGS+=(-i "$f")
    done

    # Determine clip duration from first normalized clip
    CLIP_DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "${INPUTS[0]}" | awk '{printf "%.3f", $1}')
    OFFSET=$(echo "$CLIP_DUR $XFADE_DUR" | awk '{printf "%.3f", $1 - $2}')

    FILTER=""
    PREV_LABEL="[0]"
    for ((i=1; i<N; i++)); do
      THIS_OFFSET=$(echo "$OFFSET $i" | awk '{printf "%.3f", $1 * $2}')
      NEXT_LABEL="[xf${i}]"
      FILTER+="${PREV_LABEL}[$i]xfade=transition=fade:duration=${XFADE_DUR}:offset=${THIS_OFFSET},format=yuv420p${NEXT_LABEL}; "
      PREV_LABEL="$NEXT_LABEL"
    done
    # Remove trailing "; " and the last label brackets for output map
    OUT_LABEL="${PREV_LABEL}"
    FILTER="${FILTER%; }"

    ffmpeg -y "${FF_ARGS[@]}" \
      -filter_complex "$FILTER" \
      -map "$OUT_LABEL" \
      -c:v libx264 -pix_fmt yuv420p -c:a aac \
      "$MERGED" 2>&1 | tail -5
  fi
else
  echo "[merge_reel] Merging with hard cuts (concat demuxer)..."
  ffmpeg -y -f concat -safe 0 -i "$NORM_LIST" -c copy "$MERGED" 2>&1 | tail -3
fi

echo "[merge_reel] Clips merged -> $MERGED"

# --- Step F: Lay voiceover ---
echo "[merge_reel] Overlaying voiceover: $VO_FILE"
ffmpeg -y -i "$MERGED" -i "$VO_FILE" \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -shortest \
  "$OUTPUT" 2>&1 | tail -3

echo "[merge_reel] Final reel written -> $OUTPUT"

# --- Step G: QC ---
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT" | awk '{printf "%.1f", $1}')
WIDTH_HEIGHT=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x "$OUTPUT")
CODEC=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$OUTPUT")

echo ""
echo "[merge_reel] === QC Results ==="
echo "  Duration:   ${DURATION}s  (target: ${TARGET_MIN}-${TARGET_MAX}s)"
echo "  Resolution: ${WIDTH_HEIGHT}  (target: 1080x1920)"
echo "  Codec:      ${CODEC}  (target: h264)"

PASS=true
# Use awk (already required by this script) for the float comparison so the QC gate
# does not depend on `bc`, which is absent on minimal VPS images.
DUR_OOB=$(awk -v d="$DURATION" -v lo="$TARGET_MIN" -v hi="$TARGET_MAX" 'BEGIN{print (d<lo||d>hi)?1:0}')
if [ "$DUR_OOB" = "1" ]; then
  echo "  [FAIL] Duration ${DURATION}s is outside target window ${TARGET_MIN}-${TARGET_MAX}s"
  PASS=false
fi
if [[ "$WIDTH_HEIGHT" != "1080x1920" ]]; then
  echo "  [FAIL] Resolution $WIDTH_HEIGHT != 1080x1920"
  PASS=false
fi
if [[ "$CODEC" != "h264" ]]; then
  echo "  [FAIL] Codec $CODEC != h264"
  PASS=false
fi

if [[ "$PASS" == "true" ]]; then
  echo "  [PASS] All QC checks passed."
  echo "[merge_reel] Done. Output: $OUTPUT"
  exit 0
else
  echo "[merge_reel] QC FAILED. Diagnose and re-run. Output retained at: $OUTPUT"
  exit 1
fi

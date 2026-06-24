#!/usr/bin/env bash
# OpenMontage documentary-montage FFmpeg-path RENDER PROOF (build receipt).
#
# Reproduces the PURE-FFMPEG documentary-montage compose path that
# OpenMontage's tools/video/video_stitch.py uses for the documentary-montage
# pipeline (pipeline_defs/documentary-montage.yaml compose stage):
#   1. per-beat clip NORMALIZE to a uniform spec via
#      scale=W:H:force_original_aspect_ratio=decrease,pad=... + libx264
#      (mirrors video_stitch.VideoStitch._normalize, lines ~455-459)
#   2. STITCH the beats with the FFmpeg CONCAT DEMUXER
#      (mirrors video_stitch.VideoStitch._stitch_cut, lines ~599-605)
#   3. ffprobe the output (the mandatory SOP 9.4 step 7 validation)
#
# NO Remotion. NO HyperFrames. NO headless Chromium. Pure FFmpeg only — the
# documentary-montage render path. Three narrative "beats" stand in for the
# CLIP-retrieved public-domain stock clips (real footage requires network/API;
# the FFmpeg compose path is identical regardless of clip provenance).
set -euo pipefail

OUT_DIR="${1:?usage: render-proof.sh <output_dir>}"
mkdir -p "$OUT_DIR"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

W=1280; H=720; FPS=30; CRF=23; PRESET=veryfast

# ---- Build 3 narrative "beats" (stand-ins for CLIP-retrieved stock clips) ----
# Each is generated with FFmpeg lavfi sources at a DIFFERENT native size, so the
# normalize step (scale+pad to a common WxH) is genuinely exercised — exactly
# what mixed-era documentary footage requires before a concat-demuxer stitch.
declare -a RAW=(
  "640x480:2:0x1a2b3c:beat-1-establishing"
  "1920x1080:2:0x2c1a3b:beat-2-development"
  "854x480:2:0x3b2c1a:beat-3-resolution"
)

NORM_CLIPS=()
i=0
for spec in "${RAW[@]}"; do
  size="${spec%%:*}"; rest="${spec#*:}"
  dur="${rest%%:*}"; rest="${rest#*:}"
  color="${rest%%:*}"; label="${rest#*:}"
  raw="$WORK/raw-$i.mp4"
  norm="$WORK/norm-$i.mp4"

  # Raw beat at its native (differing) resolution. testsrc2 gives moving content
  # (a real video stream, not a still) so each beat is genuinely distinct footage.
  ffmpeg -y -loglevel error \
    -f lavfi -i "testsrc2=s=$size:d=$dur:r=$FPS" \
    -f lavfi -i "sine=frequency=$((220 + i*110)):duration=$dur" \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$raw"

  # NORMALIZE to common spec (video_stitch._normalize path).
  ffmpeg -y -loglevel error -i "$raw" \
    -vf "scale=$W:$H:force_original_aspect_ratio=decrease,pad=$W:$H:(ow-iw)/2:(oh-ih)/2,setsar=1" \
    -r "$FPS" -c:v libx264 -crf "$CRF" -preset "$PRESET" -pix_fmt yuv420p \
    -c:a aac -ar 48000 "$norm"

  NORM_CLIPS+=("$norm")
  i=$((i+1))
done

# ---- STITCH via FFmpeg concat demuxer (video_stitch._stitch_cut path) ----
CONCAT_LIST="$WORK/concat_list.txt"
: > "$CONCAT_LIST"
for c in "${NORM_CLIPS[@]}"; do
  printf "file '%s'\n" "$(cd "$(dirname "$c")" && pwd)/$(basename "$c")" >> "$CONCAT_LIST"
done

OUT_MP4="$OUT_DIR/documentary-montage-render-proof.mp4"
ffmpeg -y -loglevel error \
  -f concat -safe 0 -i "$CONCAT_LIST" \
  -c copy "$OUT_MP4"

# ---- ffprobe validation (SOP 9.4 step 7 — the mandatory MP4 proof) ----
PROBE_JSON="$OUT_DIR/documentary-montage-render-proof.ffprobe.json"
ffprobe -v error \
  -show_entries "format=duration,format_name:stream=codec_type,codec_name,width,height" \
  -of json \
  "$OUT_MP4" > "$PROBE_JSON"

echo "RENDER OK: $OUT_MP4"
echo "FFPROBE  : $PROBE_JSON"
echo "FFMPEG   : $(ffmpeg -version | head -1)"
cat "$PROBE_JSON"

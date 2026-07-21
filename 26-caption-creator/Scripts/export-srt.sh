#!/bin/bash
# export-srt.sh - Export an SRT subtitle file from a video using Whisper
#
# Usage:
#   export-srt.sh --input video.mp4 --output captions.srt [--model tiny|base|small|medium|large]

set -e

INPUT=""
OUTPUT=""
MODEL="medium"

while [[ $# -gt 0 ]]; do
  case $1 in
    --input)
      INPUT="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$INPUT" || -z "$OUTPUT" ]]; then
  echo "Usage: export-srt.sh --input <video> --output <srt> [--model tiny|base|small|medium|large]"
  exit 1
fi

OUT_DIR="$(dirname "$OUTPUT")"
mkdir -p "$OUT_DIR"

TMP_DIR="$(mktemp -d "/tmp/caption_srt_XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

BASE_NAME="$(basename "$INPUT")"
BASE_STEM="${BASE_NAME%.*}"

echo "Transcribing with Whisper (model: $MODEL)..."
whisper "$INPUT" --model "$MODEL" --output_format srt --output_dir "$TMP_DIR"

GENERATED_SRT="$TMP_DIR/${BASE_STEM}.srt"

# Fallback if Whisper chose a different filename (rare)
if [[ ! -f "$GENERATED_SRT" ]]; then
  GENERATED_SRT="$(find "$TMP_DIR" -maxdepth 1 -type f -name "*.srt" | head -n 1)"
fi

if [[ -z "$GENERATED_SRT" || ! -f "$GENERATED_SRT" ]]; then
  echo "Error: Whisper did not produce an SRT file." >&2
  exit 1
fi

# T0-59: existence is not content. Whisper writes an SRT even when it recognises
# no speech; exporting that empty file hands a caption-free transcript to every
# downstream consumer. Gate on timing cues + caption text before publishing it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib-caption-guard.sh
source "$SCRIPT_DIR/lib-caption-guard.sh"
assert_srt_has_cues "$GENERATED_SRT" "$INPUT"

mv -f "$GENERATED_SRT" "$OUTPUT"

echo "SRT exported to: $OUTPUT"

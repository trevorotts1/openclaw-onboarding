#!/bin/bash
# merge-broll.sh - Merge B-roll clips with talking head video, keeping audio continuous
# Usage: merge-broll.sh --main video.mp4 --broll broll1.mp4,broll2.mp4 --insert-at 5,15,25 --output final.mp4

set -e

MAIN=""
BROLL=""
INSERT_AT=""
OUTPUT=""
KEEP_AUDIO=true
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    --main)
      MAIN="$2"
      shift 2
      ;;
    --broll)
      BROLL="$2"
      shift 2
      ;;
    --insert-at)
      INSERT_AT="$2"
      shift 2
      ;;
    --output)
      OUTPUT="$2"
      shift 2
      ;;
    --no-keep-audio)
      KEEP_AUDIO=false
      shift
      ;;
    --dry-run)
      # T2-36: INSTRUCTIONS.md:118-127 and QC.md:180-181 both present this as the
      # safety rehearsal before an irreversible render, and the parser used to
      # reject it as an unknown option.
      DRY_RUN=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$MAIN" || -z "$BROLL" || -z "$INSERT_AT" || -z "$OUTPUT" ]]; then
  echo "Usage: merge-broll.sh --main <talking-head.mp4> --broll <broll1.mp4,broll2.mp4> --insert-at <5,15,25> --output <final.mp4> [--no-keep-audio] [--dry-run]"
  echo ""
  echo "Example: Insert broll clips at 5 seconds, 15 seconds, and 25 seconds"
  echo "  --dry-run   validate every input and every insertion point, print the merge plan, render nothing"
  exit 1
fi

# ---------------------------------------------------------------------------
# T0-62 — INPUT VALIDATION. The four arguments used to be checked for
# non-emptiness only: no existence check, no size check, no media probe. The
# guided workflow stages ZERO-BYTE placeholder .mp4 files and prints a
# ready-to-run merge command pointing straight at them, so a missed placeholder
# or a failed generation reached moviepy and surfaced as a corrupt or truncated
# deliverable instead of an error where the empty input was read.
#
# Every input is now probed BEFORE any work happens. ffprobe ships with FFmpeg,
# which SKILL.md lists as a hard requirement; if it cannot run, that is reported
# as a failure and never skipped past.
# ---------------------------------------------------------------------------
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "Error: AF-MERGE-PREREQ-MISSING — ffprobe is not on PATH." >&2
  echo "  ffprobe ships with FFmpeg, which this skill requires (see SKILL.md 'Requirements')." >&2
  echo "  The input probes cannot run, so this merge is refused rather than attempted unvalidated." >&2
  exit 4
fi

# assert_video_input <path> <role>
# Non-empty regular file that ffprobe reports at least one video stream for.
assert_video_input() {
  local f="$1" role="$2" codec
  if [[ ! -f "$f" ]]; then
    echo "Error: AF-MERGE-INPUT-MISSING — ${role} not found: $f" >&2
    exit 5
  fi
  if [[ ! -s "$f" ]]; then
    echo "Error: AF-MERGE-INPUT-EMPTY — ${role} is a zero-byte file: $f" >&2
    echo "  A staged placeholder was never replaced with a real clip, or its generation failed." >&2
    exit 5
  fi
  codec="$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name \
             -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null | head -n 1)"
  if [[ -z "$codec" ]]; then
    echo "Error: AF-MERGE-INPUT-NOT-VIDEO — ${role} carries no decodable video stream: $f" >&2
    echo "  ffprobe found no video stream. Merging it would produce a corrupt or truncated deliverable." >&2
    exit 5
  fi
  echo "  ok  ${role}: $f (video codec: $codec)"
}

# media_duration <path> -> seconds (float) on stdout, empty when unknown
media_duration() {
  ffprobe -v error -show_entries format=duration \
    -of default=noprint_wrappers=1:nokey=1 "$1" 2>/dev/null | head -n 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Validating merge inputs..."
assert_video_input "$MAIN" "main video"
MAIN_DURATION="$(media_duration "$MAIN")"
if [[ -z "$MAIN_DURATION" ]]; then
  echo "Error: AF-MERGE-INPUT-NOT-VIDEO — ffprobe could not read a duration for the main video: $MAIN" >&2
  exit 5
fi
echo "  ok  main video duration: ${MAIN_DURATION}s"

# Parse B-roll files and insertion points
IFS=',' read -ra BROLL_FILES <<< "$BROLL"
IFS=',' read -ra INSERT_POINTS <<< "$INSERT_AT"

if [[ ${#BROLL_FILES[@]} != ${#INSERT_POINTS[@]} ]]; then
  echo "Error: AF-MERGE-ARITY — number of B-roll clips (${#BROLL_FILES[@]}) must match number of insertion points (${#INSERT_POINTS[@]})" >&2
  exit 1
fi

# Probe every B-roll input and validate every insertion point BEFORE any work.
# BROLL-WORKFLOW.md's "TIMESTAMP VALIDATION BEFORE MERGE" section states the rule
# this enforces: a start time must be less than the total duration.
for i in "${!BROLL_FILES[@]}"; do
  BROLL_FILE="${BROLL_FILES[$i]}"
  INSERT_TIME="${INSERT_POINTS[$i]}"

  assert_video_input "$BROLL_FILE" "B-roll clip $((i + 1))"

  if ! [[ "$INSERT_TIME" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "Error: AF-MERGE-TIMESTAMP-RANGE — insertion point $((i + 1)) is not a non-negative number: '$INSERT_TIME'" >&2
    exit 6
  fi
  if ! awk -v t="$INSERT_TIME" -v d="$MAIN_DURATION" 'BEGIN { exit !(t + 0 < d + 0) }'; then
    echo "Error: AF-MERGE-TIMESTAMP-RANGE — insertion point $((i + 1)) is ${INSERT_TIME}s, which is not inside the main video (${MAIN_DURATION}s)." >&2
    echo "  Recalculate the timestamps from the transcript before merging (see BROLL-WORKFLOW.md)." >&2
    exit 6
  fi

  echo "  plan  insert $BROLL_FILE at ${INSERT_TIME}s"
done

# T2-36: the documented safety rehearsal. Everything above has run — the probes
# and the timestamp validation — and nothing has been rendered. Stop here.
if [[ "$DRY_RUN" == true ]]; then
  echo ""
  echo "Merge plan (--dry-run; nothing was rendered):"
  echo "  main:        $MAIN (${MAIN_DURATION}s)"
  echo "  b-roll:      ${#BROLL_FILES[@]} clip(s), all probed as video"
  echo "  insert-at:   $INSERT_AT"
  echo "  keep audio:  $KEEP_AUDIO"
  echo "  would write: $OUTPUT"
  echo ""
  echo "Dry run OK — every input probed, every insertion point inside the main video."
  echo "Re-run without --dry-run to render."
  exit 0
fi

TEMP_DIR="$(mktemp -d "/tmp/broll_XXXXXX")"
trap 'rm -rf "$TEMP_DIR"' EXIT

# Extract audio from main video if keeping audio
if [[ "$KEEP_AUDIO" == true ]]; then
  echo "Extracting audio from main video..."
  "$SCRIPT_DIR/extract-audio.sh" --input "$MAIN" --output "$TEMP_DIR/audio.aac"
  AUDIO_TRACK="$TEMP_DIR/audio.aac"
fi

# The shell booleans are `true`/`false`; Python's are `True`/`False`. Interpolating
# the shell value straight into the heredoc raised `NameError: name 'true' is not
# defined` on EVERY merge, so the default (keep-audio) path could not complete at
# all. Found by 27-video-editor/test/test-merge-input-validation.sh's anti-false-fail
# control, which is the case that has to keep passing for the new probes to mean
# anything.
if [[ "$KEEP_AUDIO" == true ]]; then
  PY_KEEP_AUDIO="True"
else
  PY_KEEP_AUDIO="False"
fi

# For simplicity, use Python/MoviePy for complex merging
echo "Using Python for complex B-roll merging..."

python3 << PYTHON_EOF
import sys
sys.path.insert(0, "${SCRIPT_DIR}")
from broll_merge import merge_broll

broll_files = "${BROLL}".split(',')
insert_times = [float(x) for x in "${INSERT_AT}".split(',')]

merge_broll(
    main_video="${MAIN}",
    broll_clips=broll_files,
    insert_times=insert_times,
    output="${OUTPUT}",
    keep_main_audio=${PY_KEEP_AUDIO}
)
PYTHON_EOF

echo "Created: $OUTPUT"
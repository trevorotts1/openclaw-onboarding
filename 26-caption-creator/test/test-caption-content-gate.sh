#!/usr/bin/env bash
# test-caption-content-gate.sh — T0-59 failure contract for Skill 26.
#
# Hermetic: stubs `whisper` and `ffmpeg` on PATH, uses a temp workspace, touches
# no fleet box and makes no network call.
#
# BOTH DIRECTIONS ARE REQUIRED. A gate observed only passing has not been
# observed at all, and a gate that rejects everything is not a fix:
#   * empty transcription  -> non-zero, AF-CAPTION-EMPTY-TRANSCRIPTION, nothing rendered
#   * real transcription   -> exit 0, output produced  (anti-false-fail control)
#
# Usage: bash 26-caption-creator/test/test-caption-content-gate.sh
# Exit:  0 = every case behaved as contracted; 1 = at least one case did not.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPTS="$SKILL_DIR/Scripts"

fails=0
pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; fails=$((fails + 1)); }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/caption-gate-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

STUB="$WORK/stub-bin"
mkdir -p "$STUB"

# --- stub: whisper -----------------------------------------------------------
# Writes <output_dir>/<input-stem>.srt. WHISPER_MODE=empty emits a file with no
# cues (what the real tool does on silent audio); WHISPER_MODE=speech emits two
# real cues. WHISPER_MODE=cues-no-text emits timing lines with blank bodies.
cat > "$STUB/whisper" <<'STUBEOF'
#!/usr/bin/env bash
set -u
input=""; outdir="."
while [ $# -gt 0 ]; do
  case "$1" in
    --output_dir) outdir="$2"; shift 2 ;;
    --model|--output_format) shift 2 ;;
    -*) shift ;;
    *) input="$1"; shift ;;
  esac
done
base="$(basename "$input")"; stem="${base%.*}"
mkdir -p "$outdir"
case "${WHISPER_MODE:-speech}" in
  empty)
    : > "$outdir/$stem.srt"
    ;;
  cues-no-text)
    printf '1\n00:00:00,000 --> 00:00:02,000\n\n\n2\n00:00:02,000 --> 00:00:04,000\n\n\n' > "$outdir/$stem.srt"
    ;;
  *)
    printf '1\n00:00:00,000 --> 00:00:02,000\nHello there\n\n2\n00:00:02,000 --> 00:00:04,000\nSecond cue\n\n' > "$outdir/$stem.srt"
    ;;
esac
exit 0
STUBEOF
chmod +x "$STUB/whisper"

# --- stub: ffmpeg ------------------------------------------------------------
# Writes a non-empty file at the last positional argument (the output path).
cat > "$STUB/ffmpeg" <<'STUBEOF'
#!/usr/bin/env bash
set -u
out=""
for a in "$@"; do out="$a"; done
printf 'rendered\n' > "$out"
exit 0
STUBEOF
chmod +x "$STUB/ffmpeg"

export PATH="$STUB:$PATH"

printf 'test source\n' > "$WORK/input.mp4"

run_case() {
  # run_case <label> <expected-exit> <log-out> <command...>
  local label="$1" want="$2" log="$3"; shift 3
  local rc
  "$@" >"$log" 2>&1
  rc=$?
  if [ "$rc" -eq "$want" ]; then
    pass "$label (exit $rc)"
  else
    fail "$label — expected exit $want, got $rc"
    sed 's/^/         /' "$log"
  fi
  return 0
}

echo "== Skill 26 :: T0-59 caption content gate =="

# ---------------------------------------------------------------------------
# 1. generate-captions.sh on an EMPTY transcription must fail, name the error,
#    render nothing and announce nothing.
# ---------------------------------------------------------------------------
LOG="$WORK/gen-empty.log"
rm -f "$WORK/out-empty.mp4"
WHISPER_MODE=empty run_case "generate-captions: empty transcription is rejected" 3 "$LOG" \
  bash "$SCRIPTS/generate-captions.sh" --input "$WORK/input.mp4" --output "$WORK/out-empty.mp4"

if grep -q 'AF-CAPTION-EMPTY-TRANSCRIPTION' "$LOG"; then
  pass "generate-captions: failure is NAMED (AF-CAPTION-EMPTY-TRANSCRIPTION)"
else
  fail "generate-captions: failure is not named"
fi
if grep -q '^Created:' "$LOG"; then
  fail "generate-captions: announced 'Created:' on a caption-free run"
else
  pass "generate-captions: no output announced on a caption-free run"
fi
if [ -e "$WORK/out-empty.mp4" ]; then
  fail "generate-captions: wrote an output video from an empty transcript"
else
  pass "generate-captions: no output video written"
fi

# ---------------------------------------------------------------------------
# 2. Cues present but every body blank is still a caption-free video.
# ---------------------------------------------------------------------------
LOG="$WORK/gen-blank.log"
rm -f "$WORK/out-blank.mp4"
WHISPER_MODE=cues-no-text run_case "generate-captions: cues with no text are rejected" 3 "$LOG" \
  bash "$SCRIPTS/generate-captions.sh" --input "$WORK/input.mp4" --output "$WORK/out-blank.mp4"

# ---------------------------------------------------------------------------
# 3. ANTI-FALSE-FAIL CONTROL — a real transcription still succeeds.
# ---------------------------------------------------------------------------
LOG="$WORK/gen-ok.log"
rm -f "$WORK/out-ok.mp4"
WHISPER_MODE=speech run_case "generate-captions: a real transcription still succeeds" 0 "$LOG" \
  bash "$SCRIPTS/generate-captions.sh" --input "$WORK/input.mp4" --output "$WORK/out-ok.mp4"
if [ -s "$WORK/out-ok.mp4" ] && grep -q '^Created:' "$LOG"; then
  pass "generate-captions: real run produced and announced an output"
else
  fail "generate-captions: real run did not produce an output"
fi

# ---------------------------------------------------------------------------
# 4. export-srt.sh — same rule, both directions.
# ---------------------------------------------------------------------------
LOG="$WORK/srt-empty.log"
rm -f "$WORK/out-empty.srt"
WHISPER_MODE=empty run_case "export-srt: empty transcription is rejected" 3 "$LOG" \
  bash "$SCRIPTS/export-srt.sh" --input "$WORK/input.mp4" --output "$WORK/out-empty.srt"
if [ -e "$WORK/out-empty.srt" ]; then
  fail "export-srt: published an empty transcript"
else
  pass "export-srt: no transcript published"
fi

LOG="$WORK/srt-ok.log"
rm -f "$WORK/out-ok.srt"
WHISPER_MODE=speech run_case "export-srt: a real transcription still succeeds" 0 "$LOG" \
  bash "$SCRIPTS/export-srt.sh" --input "$WORK/input.mp4" --output "$WORK/out-ok.srt"
if [ -s "$WORK/out-ok.srt" ]; then
  pass "export-srt: real run published the transcript"
else
  fail "export-srt: real run published nothing"
fi

# ---------------------------------------------------------------------------
# 5. animated_captions.py — the third entry point, both directions.
# ---------------------------------------------------------------------------
: > "$WORK/empty.srt"
printf '1\n00:00:00,000 --> 00:00:02,000\nHello there\n\n' > "$WORK/real.srt"

LOG="$WORK/anim-empty.log"
rm -f "$WORK/anim-empty.mp4"
run_case "animated_captions: empty cue list is rejected" 3 "$LOG" \
  python3 "$SCRIPTS/animated_captions.py" --input "$WORK/input.mp4" --srt "$WORK/empty.srt" --output "$WORK/anim-empty.mp4"
if [ -e "$WORK/anim-empty.mp4" ]; then
  fail "animated_captions: rendered from an empty cue list"
else
  pass "animated_captions: rendered nothing from an empty cue list"
fi

LOG="$WORK/anim-ok.log"
rm -f "$WORK/anim-ok.mp4"
run_case "animated_captions: a real cue list still renders" 0 "$LOG" \
  python3 "$SCRIPTS/animated_captions.py" --input "$WORK/input.mp4" --srt "$WORK/real.srt" --output "$WORK/anim-ok.mp4"
if [ -s "$WORK/anim-ok.mp4" ]; then
  pass "animated_captions: real run produced an output"
else
  fail "animated_captions: real run produced no output"
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
  echo "RESULT: PASS — the caption gate fails on an empty transcription and passes on a real one."
  exit 0
fi
echo "RESULT: FAIL — $fails case(s) did not behave as contracted."
exit 1

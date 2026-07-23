#!/usr/bin/env bash
# =============================================================================
# U028 :: generate_podcast_audio.sh loudness-gate tests
#
# The audio gate must treat an UNMEASURED master as a hard failure, not a
# warning: exit 0 is contracted to mean duration AND loudness are both sane.
# These tests mock curl/ffmpeg/ffprobe (temp PATH shim, no network, no real
# ffmpeg, no secrets) and assert:
#   1. happy path: a measured, in-band master exits 0 and logs success
#   2. ffmpeg -af ebur128 fails: the script exits non-zero (UNMEASURED), the
#      success line is never reached
#   3. the R128 summary is unparseable (MEASURED_LUFS=NA): the script exits
#      non-zero, the success line is never reached
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_UNDER_TEST="$HERE/../generate_podcast_audio.sh"

bash -n "$SCRIPT_UNDER_TEST" || { echo "FAIL: bash -n"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

MOCK_BIN="$WORK/bin"
mkdir -p "$MOCK_BIN"

# --- mock curl: write fake segment bytes to -o <file>, report HTTP 200 ---
cat > "$MOCK_BIN/curl" <<'EOF'
#!/usr/bin/env bash
out=""
prev=""
for a in "$@"; do
  if [[ "$prev" == "-o" ]]; then out="$a"; fi
  prev="$a"
done
[[ -n "$out" ]] && printf 'FAKE_MP3_BYTES' > "$out"
printf '200'
EOF

# --- mock ffprobe: report a sane duration (above PODCAST_MIN_DURATION=30) ---
cat > "$MOCK_BIN/ffprobe" <<'EOF'
#!/usr/bin/env bash
echo "45.0"
EOF

# --- mock ffmpeg: dispatch on the call shape ---
#   -f concat           -> join pass: create the output (last arg)
#   loudnorm + -f null  -> measurement pass: emit the loudnorm JSON on stderr
#   libmp3lame          -> mastering pass: create the output mp3
#   ebur128             -> verify pass: emit an R128 summary on stderr, or
#                         fail / emit no summary per the FAKE_FFMPEG_* knobs
cat > "$MOCK_BIN/ffmpeg" <<'EOF'
#!/usr/bin/env bash
args="$*"
last="${@: -1}"
if [[ "$args" == *"-f concat"* ]]; then
  printf 'FAKE_WAV' > "$last"
  exit 0
fi
if [[ "$args" == *"loudnorm="* && "$args" == *"-f null"* ]]; then
  cat >&2 <<'JSON'
[Parsed_loudnorm_0]
{
	"input_i" : "-23.50",
	"input_lra" : "1.20",
	"input_tp" : "-3.50",
	"input_thresh" : "-33.50",
	"target_offset" : "0.50"
}
JSON
  exit 0
fi
if [[ "$args" == *"libmp3lame"* ]]; then
  printf 'FAKE_MASTERED_MP3' > "$last"
  exit 0
fi
if [[ "$args" == *"ebur128"* ]]; then
  if [[ "${FAKE_FFMPEG_R128_FAIL:-0}" == "1" ]]; then
    echo "mock ebur128 failure" >&2
    exit 1
  fi
  if [[ "${FAKE_FFMPEG_R128_NO_SUMMARY:-0}" == "1" ]]; then
    echo "no summary here" >&2
    exit 0
  fi
  cat >&2 <<'SUMMARY'
[Parsed_ebur128_0] Summary:

  Integrated loudness:
    I:         -15.0 LUFS
    Threshold: -25.1 LUFS
SUMMARY
  exit 0
fi
exit 0
EOF
chmod +x "$MOCK_BIN/curl" "$MOCK_BIN/ffprobe" "$MOCK_BIN/ffmpeg"

SCRIPT_FILE="$WORK/script.txt"
printf 'Hello and welcome to the show.\n\nThis is the second beat of the episode.\n' > "$SCRIPT_FILE"

run_script() {
  # env knobs: mock PATH, fake key (never printed), temp HOME so the secret-store
  # scan finds nothing. Returns the script's exit code; captures stdout+stderr.
  local outfile="$1"; shift
  env PATH="$MOCK_BIN:$PATH" \
      FISH_AUDIO_API_KEY="fake-key-for-tests" \
      HOME="$WORK/home" \
      "$@" \
      bash "$SCRIPT_UNDER_TEST" "$SCRIPT_FILE" "fake-reference-id" "s2.1-pro" "$outfile" \
      > "$WORK/out.log" 2>&1
}

fail=0

# --- Test 1: happy path — measured, in-band master exits 0 ---
if run_script "$WORK/happy.mp3"; then
  if grep -q "SUCCESS, mastered audio verified" "$WORK/out.log"; then
    echo "PASS: happy path exits 0 and reports success"
  else
    echo "FAIL: happy path exited 0 but never logged the success line"
    fail=1
  fi
else
  echo "FAIL: happy path exited non-zero"
  sed 's/^/    /' "$WORK/out.log"
  fail=1
fi

# --- Test 2: ebur128 measurement fails — hard failure, no success line ---
if run_script "$WORK/r128fail.mp3" FAKE_FFMPEG_R128_FAIL=1; then
  echo "FAIL: script exited 0 when the loudness measurement failed"
  fail=1
else
  if grep -q "SUCCESS, mastered audio verified" "$WORK/out.log"; then
    echo "FAIL: success line reached despite a failed measurement"
    fail=1
  elif grep -q "UNMEASURED" "$WORK/out.log"; then
    echo "PASS: failed measurement exits non-zero (UNMEASURED, success line never reached)"
  else
    echo "FAIL: exited non-zero but without the UNMEASURED diagnostic"
    sed 's/^/    /' "$WORK/out.log"
    fail=1
  fi
fi

# --- Test 3: unparseable R128 summary (MEASURED_LUFS=NA) — hard failure ---
if run_script "$WORK/r128na.mp3" FAKE_FFMPEG_R128_NO_SUMMARY=1; then
  echo "FAIL: script exited 0 when the loudness summary was unparseable (NA)"
  fail=1
else
  if grep -q "SUCCESS, mastered audio verified" "$WORK/out.log"; then
    echo "FAIL: success line reached despite an unparseable loudness summary"
    fail=1
  elif grep -q "UNMEASURED" "$WORK/out.log"; then
    echo "PASS: unparseable summary (NA) exits non-zero (success line never reached)"
  else
    echo "FAIL: exited non-zero but without the UNMEASURED diagnostic"
    sed 's/^/    /' "$WORK/out.log"
    fail=1
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  echo "== test_generate_podcast_audio: FAIL =="
  exit 1
fi
echo "== test_generate_podcast_audio: PASS =="

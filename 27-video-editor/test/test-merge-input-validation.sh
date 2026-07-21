#!/usr/bin/env bash
# test-merge-input-validation.sh — T0-62 + T2-36 failure contract for Skill 27.
#
# T0-62  merge-broll.sh accepted any four non-empty arguments. The guided
#        workflow stages zero-byte placeholder .mp4 files and prints a merge
#        command pointing at them, so an unreplaced placeholder was merged.
# T2-36  INSTRUCTIONS.md and QC.md both document --dry-run as the safety
#        rehearsal before an irreversible render; the parser rejected it.
#
# BOTH DIRECTIONS ARE REQUIRED:
#   * zero-byte / non-video / out-of-range input -> non-zero, named error, no render
#   * real inputs                                -> the merge proceeds (anti-false-fail)
#   * --dry-run                                  -> probes run, plan printed, no output file
#
# Hermetic: real FFmpeg generates two tiny test clips locally; the merge itself is
# stubbed out so no MoviePy install and no network are needed. No fleet box.
#
# Usage: bash 27-video-editor/test/test-merge-input-validation.sh
# Exit:  0 = every case behaved as contracted; 1 = at least one case did not.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MERGE="${MERGE_SCRIPT:-$SKILL_DIR/scripts/merge-broll.sh}"

fails=0
pass() { printf '  [PASS] %s\n' "$1"; }
fail() { printf '  [FAIL] %s\n' "$1"; fails=$((fails + 1)); }

for tool in ffmpeg ffprobe python3; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "SKIP-IMPOSSIBLE: $tool is not on PATH; this test cannot run and is NOT counted as a pass." >&2
    exit 1
  fi
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/merge-input-test.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

# --- real fixtures: two genuine video files -----------------------------------
ffmpeg -v error -y -f lavfi -i "testsrc=size=64x64:rate=10:duration=6" -pix_fmt yuv420p "$WORK/main.mp4" </dev/null
ffmpeg -v error -y -f lavfi -i "testsrc=size=64x64:rate=10:duration=2" -pix_fmt yuv420p "$WORK/broll1.mp4" </dev/null
: > "$WORK/empty.mp4"                       # zero-byte placeholder, the T0-62 case
printf 'this is not a video\n' > "$WORK/text.mp4"   # non-video payload

# --- stub the renderer --------------------------------------------------------
# merge-broll.sh imports broll_merge from its own scripts dir. Shadow that dir
# with a copy whose broll_merge.py writes a marker file instead of rendering, so
# this test measures the VALIDATION, never MoviePy.
STUBDIR="$WORK/scripts"
mkdir -p "$STUBDIR"
cp "$MERGE" "$STUBDIR/merge-broll.sh"
cat > "$STUBDIR/broll_merge.py" <<'PYEOF'
def merge_broll(main_video, broll_clips, insert_times, output, keep_main_audio=True):
    with open(output, "w") as fh:
        fh.write("rendered\n")
PYEOF
cat > "$STUBDIR/extract-audio.sh" <<'SHEOF'
#!/usr/bin/env bash
out=""
while [ $# -gt 0 ]; do
  case "$1" in --output) out="$2"; shift 2 ;; *) shift ;; esac
done
printf 'audio\n' > "$out"
SHEOF
chmod +x "$STUBDIR/extract-audio.sh"
MERGE="$STUBDIR/merge-broll.sh"

run_case() {
  # run_case <label> <expected-exit> <log> <args...>
  local label="$1" want="$2" log="$3"; shift 3
  local rc
  bash "$MERGE" "$@" >"$log" 2>&1
  rc=$?
  if [ "$rc" -eq "$want" ]; then
    pass "$label (exit $rc)"
  else
    fail "$label — expected exit $want, got $rc"
    sed 's/^/         /' "$log"
  fi
}

expect_named() {
  local log="$1" code="$2" label="$3"
  if grep -q "$code" "$log"; then
    pass "$label names $code"
  else
    fail "$label did not name $code"
  fi
}

expect_no_output() {
  local f="$1" label="$2"
  if [ -e "$f" ]; then
    fail "$label rendered an output file"
  else
    pass "$label rendered nothing"
  fi
}

echo "== Skill 27 :: T0-62 merge input validation + T2-36 --dry-run =="

# ---------------------------------------------------------------------------
# 1. A zero-byte placeholder must abort with a named error and render nothing.
# ---------------------------------------------------------------------------
LOG="$WORK/zero.log"; OUT="$WORK/out-zero.mp4"; rm -f "$OUT"
run_case "zero-byte B-roll input is rejected" 5 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/empty.mp4" --insert-at "2" --output "$OUT"
expect_named "$LOG" "AF-MERGE-INPUT-EMPTY" "zero-byte input"
expect_no_output "$OUT" "zero-byte input"

# ---------------------------------------------------------------------------
# 2. A non-video payload must abort with a named error.
# ---------------------------------------------------------------------------
LOG="$WORK/text.log"; OUT="$WORK/out-text.mp4"; rm -f "$OUT"
run_case "non-video B-roll input is rejected" 5 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/text.mp4" --insert-at "2" --output "$OUT"
expect_named "$LOG" "AF-MERGE-INPUT-NOT-VIDEO" "non-video input"
expect_no_output "$OUT" "non-video input"

# ---------------------------------------------------------------------------
# 3. A missing input must abort with a named error.
# ---------------------------------------------------------------------------
LOG="$WORK/missing.log"; OUT="$WORK/out-missing.mp4"; rm -f "$OUT"
run_case "missing B-roll input is rejected" 5 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/nope.mp4" --insert-at "2" --output "$OUT"
expect_named "$LOG" "AF-MERGE-INPUT-MISSING" "missing input"

# ---------------------------------------------------------------------------
# 4. An insertion point past the end of the main video must abort.
#    (BROLL-WORKFLOW.md: "Start time must be less than total duration".)
# ---------------------------------------------------------------------------
LOG="$WORK/ts.log"; OUT="$WORK/out-ts.mp4"; rm -f "$OUT"
run_case "out-of-range insertion point is rejected" 6 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/broll1.mp4" --insert-at "9999" --output "$OUT"
expect_named "$LOG" "AF-MERGE-TIMESTAMP-RANGE" "out-of-range timestamp"
expect_no_output "$OUT" "out-of-range timestamp"

LOG="$WORK/ts2.log"; OUT="$WORK/out-ts2.mp4"; rm -f "$OUT"
run_case "non-numeric insertion point is rejected" 6 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/broll1.mp4" --insert-at "later" --output "$OUT"
expect_named "$LOG" "AF-MERGE-TIMESTAMP-RANGE" "non-numeric timestamp"

# ---------------------------------------------------------------------------
# 5. T2-36 — the documented rehearsal flag is accepted, runs the probes, prints
#    the plan and renders nothing.
# ---------------------------------------------------------------------------
LOG="$WORK/dry.log"; OUT="$WORK/out-dry.mp4"; rm -f "$OUT"
run_case "--dry-run is accepted" 0 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/broll1.mp4" --insert-at "2" --output "$OUT" --dry-run
expect_no_output "$OUT" "--dry-run"
if grep -q 'Merge plan' "$LOG" && grep -q 'video codec' "$LOG"; then
  pass "--dry-run printed the plan and the probe results"
else
  fail "--dry-run did not print the plan and the probe results"
fi

# A rehearsal that cannot pass the probes must still fail.
LOG="$WORK/dry-bad.log"
run_case "--dry-run still fails on a bad input" 5 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/empty.mp4" --insert-at "2" --output "$WORK/out-dry-bad.mp4" --dry-run

# ---------------------------------------------------------------------------
# 6. ANTI-FALSE-FAIL CONTROL — real inputs and a valid timestamp still merge.
# ---------------------------------------------------------------------------
LOG="$WORK/ok.log"; OUT="$WORK/out-ok.mp4"; rm -f "$OUT"
run_case "real inputs still merge" 0 "$LOG" \
  --main "$WORK/main.mp4" --broll "$WORK/broll1.mp4" --insert-at "2" --output "$OUT"
if [ -s "$OUT" ]; then
  pass "real merge produced an output"
else
  fail "real merge produced no output"
fi

echo "=================================================="
if [ "$fails" -eq 0 ]; then
  echo "RESULT: PASS — bad inputs abort with named errors, --dry-run rehearses, real merges still run."
  exit 0
fi
echo "RESULT: FAIL — $fails case(s) did not behave as contracted."
exit 1

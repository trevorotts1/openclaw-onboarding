#!/usr/bin/env bash
# Folded from .github/workflows/unwired-checks-guard.yml (job "Skill 25 — video-creator contract tests (PR #686's 16 blockers)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Install the system video tooling the suite actually needs
echo "--- step: Install the system video tooling the suite actually needs"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unwired-checks-guard: step \"Install the system video tooling the suite actually needs\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# FFmpeg and ImageMagick are not optional here — they are the exact
# system prerequisites 25-video-creator/INSTALL.md Step 1 mandates
# ("Ubuntu / Debian: sudo apt-get install -y ffmpeg imagemagick").
# Three of the 93 tests reach them for real, so a runner without them
# is a runner that cannot run the suite the workflow claims to run:
#   * test_provider_contracts.py::test_download_accepts_real_decodable_
#     positive_duration_video shells out to the `ffmpeg` binary to build
#     a genuine, decodable fixture clip — no ffmpeg, FileNotFoundError.
#   * test_qc_contracts.py's two cases invoke qc-video-creator.sh, whose
#     Rule-driven install QC hard-asserts `command -v ffmpeg` and
#     `command -v convert` (ImageMagick). Missing tooling -> the skill's
#     own QC exits 1 -> the contract that mock/local and a keyed real
#     provider both pass QC cannot be satisfied.
# Installing them is the same class of act as pinning moviepy below:
# provisioning the documented runtime so the real tests run for real.
# It is never a skip and never a gate change — all 93 still execute and
# must pass.
sudo apt-get update
sudo apt-get install -y ffmpeg imagemagick
command -v ffmpeg  >/dev/null || { echo "ffmpeg did not install"; exit 1; }
command -v convert >/dev/null || { echo "ImageMagick (convert) did not install"; exit 1; }
ffmpeg -version | head -1
)
( # step: Install the pinned runtime the suite actually needs
echo "--- step: Install the pinned runtime the suite actually needs"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unwired-checks-guard: step \"Install the pinned runtime the suite actually needs\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# MoviePy v1 is not a preference. 25-video-creator/INSTALL.md pins
# moviepy==1.0.3 because the scripts import `moviepy.editor`, which v2
# deleted. Six of the 93 tests render real frames through
# moviepy.editor.ColorClip to prove two advertised transitions are not
# byte-identical; under v2 they raise ModuleNotFoundError. The correct
# fix is the pin, never a skip — those six are the only tests that
# measure rendering at all.
python3 -m pip install --upgrade pip
python3 -m pip install "moviepy==1.0.3" numpy requests pytest
python3 -c 'from moviepy.editor import ColorClip; print("moviepy.editor import OK")'
)
( # step: Run the Skill 25 contract tests
echo "--- step: Run the Skill 25 contract tests"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unwired-checks-guard: step \"Run the Skill 25 contract tests\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m pytest 25-video-creator/tests -q --junitxml=skill25-report.xml
)
( # step: Anti-vacuity — the original 93-test floor actually EXECUTED
echo "--- step: Anti-vacuity — the original 93-test floor actually EXECUTED"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unwired-checks-guard: step \"Anti-vacuity — the original 93-test floor actually EXECUTED\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# A green pytest that collected nothing is the silent-success bug in a
# different hat. Read the JUnit XML structurally (no log scraping) and
# require the floor the suite shipped with.
python3 - <<'PY'
import sys, xml.etree.ElementTree as ET
root = ET.parse("skill25-report.xml").getroot()
suites = [root] if root.tag == "testsuite" else list(root)
total = sum(int(s.get("tests", 0)) for s in suites)
errors = sum(int(s.get("errors", 0)) for s in suites)
failures = sum(int(s.get("failures", 0)) for s in suites)
skipped = sum(int(s.get("skipped", 0)) for s in suites)
executed = total - skipped
print(f"collected={total} executed={executed} failures={failures} "
      f"errors={errors} skipped={skipped}")
if errors or failures:
    sys.exit("Skill 25 contract tests reported failures/errors.")
if executed < 93:
    sys.exit(f"Only {executed} Skill 25 contract tests executed; the suite "
             f"ships 93. Tests were removed, skipped or failed to collect. "
             f"If tests were intentionally retired, lower this floor in the "
             f"same change and say why.")
print(f"  OK  {executed} contract tests executed (floor 93)")
PY
)
( # step: Suite self-test — a real Skill 25 defect must go RED
echo "--- step: Suite self-test — a real Skill 25 defect must go RED"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unwired-checks-guard: step \"Suite self-test — a real Skill 25 defect must go RED\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
# Re-advertise `slide_left` in Transitions.AVAILABLE. That is the exact
# PR #686 defect: four slide directions were advertised while
# concatenate_videoclips(method="compose") re-centred every clip and
# dropped the position animation, so a caller asking for slide_left
# silently got something else. The suite must catch it.
#
# The defect is injected into a THROWAWAY COPY and reached through the
# suite's own SKILL25_ROOT hook (see 25-video-creator/tests/conftest.py),
# so the checkout is never mutated.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp -R 25-video-creator "$TMP/25-video-creator"
python3 - "$TMP/25-video-creator/scripts/transitions.py" <<'PY'
import sys
p = sys.argv[1]
src = open(p).read()
old = ("    AVAILABLE = [\n"
       "        'fade',\n"
       "        'wipe_left', 'wipe_right', 'wipe_up', 'wipe_down',\n"
       "        'none'\n"
       "    ]")
if src.count(old) != 1:
    sys.exit("self-test fixture stale: Transitions.AVAILABLE no longer has "
             "the expected shape; update this injection so the red-proof "
             "keeps proving something.")
open(p, "w").write(src.replace(old, old.replace(
    "        'none'\n", "        'slide_left',\n        'none'\n")))
print("injected: slide_left re-advertised in Transitions.AVAILABLE")
PY
if SKILL25_ROOT="$TMP/25-video-creator" \
   python3 -m pytest 25-video-creator/tests -q >"$TMP/out.txt" 2>&1; then
  echo "VACUOUS SUITE: re-advertising an unimplemented transition passed." >&2
  tail -40 "$TMP/out.txt" >&2
  exit 1
fi
grep -q "test_every_advertised_transition_is_implemented_or_rejected" "$TMP/out.txt" || {
  echo "Suite failed, but not on the injected transition defect:" >&2
  tail -40 "$TMP/out.txt" >&2
  exit 1
}
echo "  ✓ the Skill 25 suite goes red on a real transition-aliasing defect"
)

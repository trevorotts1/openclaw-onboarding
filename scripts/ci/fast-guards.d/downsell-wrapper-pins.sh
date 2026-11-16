#!/usr/bin/env bash
# Folded from .github/workflows/downsell-wrapper-pins.yml (job "downsell-wrapper-pins"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Install pytest and pillow
echo "--- step: Install pytest and pillow"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards downsell-wrapper-pins: step \"Install pytest and pillow\" failed (exit $fg_rc)"' EXIT
python -m pip install pytest pillow==10.4.0 jsonschema==4.10.3
)
( # step: Control - one changed byte of validate_downsell.py must turn the pin test red
echo "--- step: Control - one changed byte of validate_downsell.py must turn the pin test red"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards downsell-wrapper-pins: step \"Control - one changed byte of validate_downsell.py must turn the pin test red\" failed (exit $fg_rc)"' EXIT
set -uo pipefail
target=81-signature-downsell/validators/validate_downsell.py
printf ' ' >> "$target"
rc=0
python3 -m pytest 49-signature-funnel/scripts/test_downsell_wrapper.py -q -k DownsellPinTests || rc=$?
git checkout -- "$target"
git diff --exit-code -- "$target"
if [ "$rc" -ne 1 ]; then
  echo "control: expected pytest exit 1 (tests failed) with a tampered validator, got $rc"
  exit 1
fi
echo "control: tampered validator turned the pin test red (exit 1)"
)
( # step: D1 wrapper suite (pins equal sha256 of the Skill 81 files)
echo "--- step: D1 wrapper suite (pins equal sha256 of the Skill 81 files)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards downsell-wrapper-pins: step \"D1 wrapper suite (pins equal sha256 of the Skill 81 files)\" failed (exit $fg_rc)"' EXIT
python3 -m pytest 49-signature-funnel/scripts/test_downsell_wrapper.py -q
)
( # step: Thank-you translator suite (issues 63 and 65)
echo "--- step: Thank-you translator suite (issues 63 and 65)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards downsell-wrapper-pins: step \"Thank-you translator suite (issues 63 and 65)\" failed (exit $fg_rc)"' EXIT
python3 49-signature-funnel/scripts/test_thankyou_translator.py
)

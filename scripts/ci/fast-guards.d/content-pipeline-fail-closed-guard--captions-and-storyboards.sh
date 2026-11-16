#!/usr/bin/env bash
# Folded from .github/workflows/content-pipeline-fail-closed-guard.yml (job "T0-59/T0-60: captions gated on content, storyboard failures exit non-zero"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax-check the shell entry points
echo "--- step: Syntax-check the shell entry points"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--captions-and-storyboards: step \"Syntax-check the shell entry points\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n 26-caption-creator/Scripts/generate-captions.sh
bash -n 26-caption-creator/Scripts/export-srt.sh
bash -n 26-caption-creator/Scripts/lib-caption-guard.sh
bash -n 26-caption-creator/test/test-caption-content-gate.sh
echo "OK: shell syntax"
)
( # step: Compile the Python entry points
echo "--- step: Compile the Python entry points"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--captions-and-storyboards: step \"Compile the Python entry points\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m py_compile 26-caption-creator/Scripts/animated_captions.py
python3 -m py_compile 24-storyboard-writer/scripts/create_storyboard.py
echo "OK: python compiles"
)
( # step: T0-59 — the caption gate fails on an empty transcription and passes on a real one
echo "--- step: T0-59 — the caption gate fails on an empty transcription and passes on a real one"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--captions-and-storyboards: step \"T0-59 — the caption gate fails on an empty transcription and passes on a real one\" failed (exit $fg_rc)"' EXIT
bash 26-caption-creator/test/test-caption-content-gate.sh
)
( # step: T0-60 — the storyboard failure path exits non-zero on stderr, and real runs still work
echo "--- step: T0-60 — the storyboard failure path exits non-zero on stderr, and real runs still work"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--captions-and-storyboards: step \"T0-60 — the storyboard failure path exits non-zero on stderr, and real runs still work\" failed (exit $fg_rc)"' EXIT
python3 24-storyboard-writer/test/test_storyboard_failure_contract.py
)

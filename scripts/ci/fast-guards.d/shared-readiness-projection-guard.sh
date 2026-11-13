#!/usr/bin/env bash
# Folded from .github/workflows/shared-readiness-projection-guard.yml (job "T-40 — shared readiness projection acceptance suite"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: T-40 acceptance suite (explicit file path)
echo "--- step: T-40 acceptance suite (explicit file path)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards shared-readiness-projection-guard: step \"T-40 acceptance suite (explicit file path)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 tests/unit/shared-readiness-projection.test.py
echo "✓ tests/unit/shared-readiness-projection.test.py all pass"
)

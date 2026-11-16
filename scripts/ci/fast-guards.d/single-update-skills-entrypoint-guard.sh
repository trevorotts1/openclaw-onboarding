#!/usr/bin/env bash
# Folded from .github/workflows/single-update-skills-entrypoint-guard.yml (job "scripts/update-skills.sh can never succeed; no live doc points at it"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run single-entrypoint guard
echo "--- step: Run single-entrypoint guard"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards single-update-skills-entrypoint-guard: step \"Run single-entrypoint guard\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/test-single-update-skills-entrypoint.sh
echo "single-update-skills-entrypoint-guard: PASS"
)

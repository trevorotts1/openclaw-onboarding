#!/usr/bin/env bash
# Folded from .github/workflows/full-funnel-pipeline.yml (job "funnel_rollback executable (not prose-only)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export PYTHONUNBUFFERED=1
( # step: Assert funnel_rollback has an executable implementation
echo "--- step: Assert funnel_rollback has an executable implementation"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--funnel-rollback-prose-guard: step \"Assert funnel_rollback has an executable implementation\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
test -f 23-ai-workforce-blueprint/full-funnel-pipeline/funnel_rollback.py
grep -q "def run_funnel_rollback" 23-ai-workforce-blueprint/full-funnel-pipeline/funnel_rollback.py
echo "✓ SOP-07 §7 funnel_rollback is implemented in code, not prose-only"
)

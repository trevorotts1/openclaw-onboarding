#!/usr/bin/env bash
# Folded from .github/workflows/hook-enforcement-parity-guard.yml (job "hook-enforcement parity guard"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run hook enforcement parity guard
echo "--- step: Run hook enforcement parity guard"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards hook-enforcement-parity-guard: step \"Run hook enforcement parity guard\" failed (exit $fg_rc)"' EXIT
bash scripts/guard-hook-enforcement-parity.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/local-embedder-guard.yml (job "Skill 76 wire.sh + re-pinner guards (mocked)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax
echo "--- step: Syntax"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards local-embedder-guard: step \"Syntax\" failed (exit $fg_rc)"' EXIT
bash -n 76-local-embedder/wire.sh
bash -n 76-local-embedder/tests/test-local-embedder.sh
)
( # step: Run the Skill 76 tests
echo "--- step: Run the Skill 76 tests"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards local-embedder-guard: step \"Run the Skill 76 tests\" failed (exit $fg_rc)"' EXIT
bash 76-local-embedder/tests/test-local-embedder.sh
)

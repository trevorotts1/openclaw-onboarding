#!/usr/bin/env bash
# Folded from .github/workflows/installer-contracts-guard.yml (job "A46 — every configuration block an installer merges must parse (T2-22)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Self-test the checker (5 directions)
echo "--- step: Self-test the checker (5 directions)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards installer-contracts-guard--installer-config-blocks: step \"Self-test the checker (5 directions)\" failed (exit $fg_rc)"' EXIT
python3 scripts/check-installer-config-blocks.py --self-test
)
( # step: Every configuration block parses
echo "--- step: Every configuration block parses"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards installer-contracts-guard--installer-config-blocks: step \"Every configuration block parses\" failed (exit $fg_rc)"' EXIT
python3 scripts/check-installer-config-blocks.py
)

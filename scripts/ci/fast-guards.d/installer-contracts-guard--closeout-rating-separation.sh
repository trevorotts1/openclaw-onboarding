#!/usr/bin/env bash
# Folded from .github/workflows/installer-contracts-guard.yml (job "A47 — materialisation must not write a rubric score (T0-08)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Install jq
echo "--- step: Install jq"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards installer-contracts-guard--closeout-rating-separation: step \"Install jq\" failed (exit $fg_rc)"' EXIT
sudo apt-get update -qq && sudo apt-get install -y -qq jq
)
( # step: Closeout ghost + rating tests, including the A47 separation cases
echo "--- step: Closeout ghost + rating tests, including the A47 separation cases"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards installer-contracts-guard--closeout-rating-separation: step \"Closeout ghost + rating tests, including the A47 separation cases\" failed (exit $fg_rc)"' EXIT
bash 37-zhc-closeout/scripts/test-closeout-ghost-and-rating.sh
)

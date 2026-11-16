#!/usr/bin/env bash
# Folded from .github/workflows/installer-contracts-guard.yml (job "A46 — skill 39 provider-status producer and consumer share one contract (T2-32)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Path, capability names, state shape, round trip, absent artifact
echo "--- step: Path, capability names, state shape, round trip, absent artifact"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards installer-contracts-guard--provider-status-contract: step \"Path, capability names, state shape, round trip, absent artifact\" failed (exit $fg_rc)"' EXIT
bash scripts/test-provider-status-contract.sh
)

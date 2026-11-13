#!/usr/bin/env bash
# Folded from .github/workflows/installer-contracts-guard.yml (job "A45 — credentials land where the skill's own check reads them (T2-21)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Both directions per skill, plus the static no-legacy-write check
echo "--- step: Both directions per skill, plus the static no-legacy-write check"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards installer-contracts-guard--credential-store: step \"Both directions per skill, plus the static no-legacy-write check\" failed (exit $fg_rc)"' EXIT
bash scripts/test-installer-credential-store.sh
)

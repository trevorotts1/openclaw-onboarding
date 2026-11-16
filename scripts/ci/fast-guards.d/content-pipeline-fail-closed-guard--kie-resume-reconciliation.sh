#!/usr/bin/env bash
# Folded from .github/workflows/content-pipeline-fail-closed-guard.yml (job "T0-58: a resumed slide is reconciled against disk"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: The Skill 46 suite, including the resume-path outcome rule
echo "--- step: The Skill 46 suite, including the resume-path outcome rule"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards content-pipeline-fail-closed-guard--kie-resume-reconciliation: step \"The Skill 46 suite, including the resume-path outcome rule\" failed (exit $fg_rc)"' EXIT
node 46-kie-callback-relay/test/security.test.mjs
)

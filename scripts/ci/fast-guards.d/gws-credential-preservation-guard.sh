#!/usr/bin/env bash
# Folded from .github/workflows/gws-credential-preservation-guard.yml (job "update/verify path cannot wipe ~/.config/gws* or secrets/.env"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run gws credential-preservation regression test
echo "--- step: Run gws credential-preservation regression test"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards gws-credential-preservation-guard: step \"Run gws credential-preservation regression test\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/test-gws-credential-preservation.sh
echo "gws-credential-preservation-guard: PASS"
)

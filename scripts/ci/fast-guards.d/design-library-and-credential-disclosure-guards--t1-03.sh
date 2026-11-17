#!/usr/bin/env bash
# Folded from .github/workflows/design-library-and-credential-disclosure-guards.yml (job "T1-03: credential checks report presence, never a value"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax-check the test
echo "--- step: Syntax-check the test"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards design-library-and-credential-disclosure-guards--t1-03: step \"Syntax-check the test\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n tests/unit/credential-presence-only-docs.test.sh
echo "OK: test parses"
)
( # step: Every documented credential check is presence-only
echo "--- step: Every documented credential check is presence-only"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards design-library-and-credential-disclosure-guards--t1-03: step \"Every documented credential check is presence-only\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash tests/unit/credential-presence-only-docs.test.sh
)

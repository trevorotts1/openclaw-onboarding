#!/usr/bin/env bash
# Folded from .github/workflows/type-f-census-guard.yml (job "guard"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Type-f census guard (warn-mode)
echo "--- step: Type-f census guard (warn-mode)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards type-f-census-guard: step \"Type-f census guard (warn-mode)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 scripts/qc-assert-no-type-f-census.py
echo "✓ Type-f census guard completed (warn-mode)"
)
( # step: Negative self-test (guard must fail on planted violation)
echo "--- step: Negative self-test (guard must fail on planted violation)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards type-f-census-guard: step \"Negative self-test (guard must fail on planted violation)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/tests/type-f-census-guard.negative-fixture.sh
echo "✓ Negative self-test passed (guard exits 1 on a planted violation)"
)

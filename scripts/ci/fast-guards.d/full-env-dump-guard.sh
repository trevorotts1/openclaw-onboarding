#!/usr/bin/env bash
# Folded from .github/workflows/full-env-dump-guard.yml (job "full-env-dump guard (pm2 jlist/prettylist/--json ban, warn-mode)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Run full-env-dump guard (warn-mode)
echo "--- step: Run full-env-dump guard (warn-mode)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-env-dump-guard: step \"Run full-env-dump guard (warn-mode)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 scripts/qc-assert-no-full-env-dump.py
echo "full-env-dump guard: warn-mode pass (scanned, violations reported but not blocking)"
)
( # step: Negative self-test (shell + Python list-form fixtures)
echo "--- step: Negative self-test (shell + Python list-form fixtures)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-env-dump-guard: step \"Negative self-test (shell + Python list-form fixtures)\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash scripts/tests/full-env-dump-guard.negative-fixture.sh
echo "full-env-dump guard negative self-test: both shell and Python list-form fixtures detected"
)

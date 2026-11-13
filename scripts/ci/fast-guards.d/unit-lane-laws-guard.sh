#!/usr/bin/env bash
# Folded from .github/workflows/unit-lane-laws-guard.yml (job "Control suite (the gate must discriminate)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Syntax
echo "--- step: Syntax"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unit-lane-laws-guard: step \"Syntax\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
bash -n scripts/qc-assert-unit-lane-laws.sh
bash -n tests/unit/qc-assert-unit-lane-laws.test.sh
echo "syntax OK"
)
( # step: Control suite
echo "--- step: Control suite"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards unit-lane-laws-guard: step \"Control suite\" failed (exit $fg_rc)"' EXIT
set -uo pipefail
bash tests/unit/qc-assert-unit-lane-laws.test.sh
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "::error::control suite failed (rc=$rc) — the gate is not trustworthy"
  exit 1
fi
echo "control suite PASSED"
)

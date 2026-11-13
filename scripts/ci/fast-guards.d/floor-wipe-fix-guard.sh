#!/usr/bin/env bash
# Folded from .github/workflows/floor-wipe-fix-guard.yml (job "P2-06 floor-wipe fix (5 hermetic suites)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export OPENCLAW_PLATFORM=mac
( # step: Run the P2-06 suites (each exit 0 required)
echo "--- step: Run the P2-06 suites (each exit 0 required)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards floor-wipe-fix-guard: step \"Run the P2-06 suites (each exit 0 required)\" failed (exit $fg_rc)"' EXIT
set -uo pipefail
rc=0

echo "======================================================================"
echo "RUN: 23-ai-workforce-blueprint/scripts/test-naming-map-corruption-fail-closed.sh"
echo "======================================================================"
if bash 23-ai-workforce-blueprint/scripts/test-naming-map-corruption-fail-closed.sh; then
  echo "PASS: test-naming-map-corruption-fail-closed.sh"
else
  echo "FAIL: test-naming-map-corruption-fail-closed.sh exited non-zero" >&2
  rc=1
fi

echo "======================================================================"
echo "RUN: 23-ai-workforce-blueprint/scripts/test-materialize-missing-departments.sh"
echo "======================================================================"
if bash 23-ai-workforce-blueprint/scripts/test-materialize-missing-departments.sh; then
  echo "PASS: test-materialize-missing-departments.sh"
else
  echo "FAIL: test-materialize-missing-departments.sh exited non-zero" >&2
  rc=1
fi

echo "======================================================================"
echo "RUN: 23-ai-workforce-blueprint/scripts/test-materialize-missing-departments-join.sh"
echo "======================================================================"
if bash 23-ai-workforce-blueprint/scripts/test-materialize-missing-departments-join.sh; then
  echo "PASS: test-materialize-missing-departments-join.sh"
else
  echo "FAIL: test-materialize-missing-departments-join.sh exited non-zero" >&2
  rc=1
fi

echo "======================================================================"
echo "RUN: scripts/probe/test-p206-floor-short-probe.sh"
echo "======================================================================"
if bash scripts/probe/test-p206-floor-short-probe.sh; then
  echo "PASS: test-p206-floor-short-probe.sh"
else
  echo "FAIL: test-p206-floor-short-probe.sh exited non-zero" >&2
  rc=1
fi

echo "======================================================================"
echo "RUN: 23-ai-workforce-blueprint/scripts/test-floor-fill-vertical-gate.sh"
echo "======================================================================"
if bash 23-ai-workforce-blueprint/scripts/test-floor-fill-vertical-gate.sh; then
  echo "PASS: test-floor-fill-vertical-gate.sh"
else
  echo "FAIL: test-floor-fill-vertical-gate.sh exited non-zero" >&2
  rc=1
fi

echo "======================================================================"
if [ "$rc" -eq 0 ]; then
  echo "ALL 5 P2-06 FLOOR-WIPE-FIX SUITES PASSED"
else
  echo "ONE OR MORE P2-06 FLOOR-WIPE-FIX SUITES FAILED" >&2
fi
exit "$rc"
)

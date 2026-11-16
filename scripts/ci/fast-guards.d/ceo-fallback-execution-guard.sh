#!/usr/bin/env bash
# Folded from .github/workflows/ceo-fallback-execution-guard.yml (job "offline-regressions"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Verify policy, managed upgrades, plugin imports and runtime ownership
echo "--- step: Verify policy, managed upgrades, plugin imports and runtime ownership"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ceo-fallback-execution-guard: step \"Verify policy, managed upgrades, plugin imports and runtime ownership\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/test_ceo_execution_policy.py
python3 tests/unit/test_ceo_runtime_bindings.py
bash -n scripts/apply-routing-fix.sh scripts/apply-fleet-standards.sh scripts/verify-routing.sh update-skills.sh
)
( # step: Verify existing workforce repair and both fresh registry formats
echo "--- step: Verify existing workforce repair and both fresh registry formats"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards ceo-fallback-execution-guard: step \"Verify existing workforce repair and both fresh registry formats\" failed (exit $fg_rc)"' EXIT
export STANDARD_FIRST_ONBOARDING=1
bash 32-command-center-setup/scripts/materialize-dept-agents-roster-shape.test.sh
bash 32-command-center-setup/scripts/materialize-dept-agents-company-scope.test.sh
ONB_TEST_REGISTRY=list bash 23-ai-workforce-blueprint/scripts/test-build-standard-first-roundtrip.sh
ONB_TEST_REGISTRY=entries bash 23-ai-workforce-blueprint/scripts/test-build-standard-first-roundtrip.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/presentation-release-matrix.yml (job "Live GHL smoke stays refused in CI (NOT VERIFIED)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Prove live smoke refuses without sandbox authorization
echo "--- step: Prove live smoke refuses without sandbox authorization"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards presentation-release-matrix--live-smoke-refusal: step \"Prove live smoke refuses without sandbox authorization\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m pip install --quiet --disable-pip-version-check pytest==8.3.4
cd 23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests
python3 -m pytest test_pres043_release_matrix.py::test_live_ghl_smoke_requires_sandbox_credentials -q
)

#!/usr/bin/env bash
# Folded from .github/workflows/skill23-provisioning-tests.yml (job "Skill-23 provisioning tests (12 hermetic suites)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export OPENCLAW_PLATFORM=mac
( # step: Run the provisioning suites (each exit 0 required)
echo "--- step: Run the provisioning suites (each exit 0 required)"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards skill23-provisioning-tests: step \"Run the provisioning suites (each exit 0 required)\" failed (exit $fg_rc)"' EXIT
set -uo pipefail
SCRIPTS="23-ai-workforce-blueprint/scripts"
SUITES=(
  test-department-floor.sh
  test-decline-provenance-guard.sh
  test-reconciliation-engine.sh
  test-ws4-departments.sh
  test-department-instantiation.sh
  prove-web-parity.sh
  test-phantom-dept-collision-gate.sh
  test-chosen-departments-artifact.sh
  test-vertical-derivation-guard.sh
  test-record-vertical-pack.sh
  test-pack-keyword-variants.sh
  test-u109-floor-wipe-regression.sh
  test-u110-optout-caller-wiring.sh
  test-reconcile-orphan-library-files.sh
  test-standard-placeholder.sh
  test-standard-placeholder-install-gate.sh
)
rc=0
for s in "${SUITES[@]}"; do
  path="$SCRIPTS/$s"
  echo "======================================================================"
  echo "RUN: $s"
  echo "======================================================================"
  if [ ! -f "$path" ]; then
    echo "FATAL: $path not found" >&2
    rc=1
    continue
  fi
  if bash "$path"; then
    echo "PASS: $s"
  else
    echo "FAIL: $s exited non-zero" >&2
    rc=1
  fi
done
echo "======================================================================"
if [ "$rc" -eq 0 ]; then
  echo "ALL ${#SUITES[@]} SKILL-23 PROVISIONING SUITES PASSED"
else
  echo "ONE OR MORE SKILL-23 PROVISIONING SUITES FAILED" >&2
fi
exit "$rc"
)
( # step: Install OpenClaw CLI (config validate only)
echo "--- step: Install OpenClaw CLI (config validate only)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards skill23-provisioning-tests: step \"Install OpenClaw CLI (config validate only)\" failed (exit $fg_rc)"' EXIT
npm install -g --no-audit --no-fund --ignore-scripts openclaw@2026.9.4
)
( # step: Non-destructive build on an existing box
echo "--- step: Non-destructive build on an existing box"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards skill23-provisioning-tests: step \"Non-destructive build on an existing box\" failed (exit $fg_rc)"' EXIT
export REQUIRE_OPENCLAW_VALIDATE=1
openclaw --version
python3 tests/unit/test_skill23_build_nondestructive.py
(cd 23-ai-workforce-blueprint/scripts && python3 test_role_workspace_symlinks.py)
)

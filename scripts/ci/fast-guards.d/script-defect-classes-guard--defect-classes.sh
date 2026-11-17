#!/usr/bin/env bash
# Folded from .github/workflows/script-defect-classes-guard.yml (job "defect classes A-G stay fixed"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: A — agents.entries roster readers/writers
echo "--- step: A — agents.entries roster readers/writers"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"A — agents.entries roster readers/writers\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/agents-entries-roster-readers.test.py -v
python3 tests/unit/agents-entries-remaining-readers.test.py -v
)
( # step: B — mission-control.db decoy resolver
echo "--- step: B — mission-control.db decoy resolver"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"B — mission-control.db decoy resolver\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/cc-db-decoy-resolver.test.py -v
)
( # step: C — GNU stat first (native GNU on this runner)
echo "--- step: C — GNU stat first (native GNU on this runner)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"C — GNU stat first (native GNU on this runner)\" failed (exit $fg_rc)"' EXIT
bash tests/unit/gnu-stat-first.test.sh
)
( # step: D — retire on a separate workspace departments tree
echo "--- step: D — retire on a separate workspace departments tree"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"D — retire on a separate workspace departments tree\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/retire-decline-separate-workspace.test.py -v
)
( # step: E — update.sh path stamps commandCenterBuildFresh
echo "--- step: E — update.sh path stamps commandCenterBuildFresh"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"E — update.sh path stamps commandCenterBuildFresh\" failed (exit $fg_rc)"' EXIT
bash tests/unit/cc-update-path-build-fresh.test.sh
bash tests/unit/cc-done-degraded-retry-gate.test.sh
)
( # step: F — embedding probe vs shipped asset
echo "--- step: F — embedding probe vs shipped asset"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"F — embedding probe vs shipped asset\" failed (exit $fg_rc)"' EXIT
python3 tests/unit/embedding-probe-shipped-asset.test.py -v
)
( # step: G — platform detection parity
echo "--- step: G — platform detection parity"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"G — platform detection parity\" failed (exit $fg_rc)"' EXIT
bash tests/unit/platform-detection-parity.test.sh
)
( # step: H — wiring gate skips department runtime dirs, still gates real roles
echo "--- step: H — wiring gate skips department runtime dirs, still gates real roles"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards script-defect-classes-guard--defect-classes: step \"H — wiring gate skips department runtime dirs, still gates real roles\" failed (exit $fg_rc)"' EXIT
bash 23-ai-workforce-blueprint/scripts/test-wiring-gate-role-dir-walk.sh
)

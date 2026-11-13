#!/usr/bin/env bash
# Folded from .github/workflows/full-funnel-pipeline.yml (job "seed-workspaces departments normalizer (converge Step-4 crash fix)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
export PYTHONUNBUFFERED=1
( # step: Install pytest
echo "--- step: Install pytest"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--seed-normalize: step \"Install pytest\" failed (exit $fg_rc)"' EXIT
pip install pytest
)
( # step: Run normalizer regression test
echo "--- step: Run normalizer regression test"
set -e
set -o pipefail
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards full-funnel-pipeline--seed-normalize: step \"Run normalizer regression test\" failed (exit $fg_rc)"' EXIT
set -euo pipefail
python3 -m pytest 32-command-center-setup/scripts/test_seed_workspaces_normalize.py -q
echo "✓ departments.json str/dict/dict-of-dicts shapes all normalize"
python3 -m pytest 32-command-center-setup/scripts/test_seed_workspaces_installer_hardening.py -q
echo "✓ installer hardening: archived workspaces skipped, name match updates, company split logged"
)

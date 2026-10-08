#!/usr/bin/env bash
# Folded from .github/workflows/anthology-shared-run-dir-guard.yml (job "Anthology stages share ONE per-participant run dir (Skill 54's first gate proven both ways)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Install pytest
set -e
python3 -m pip install --quiet --disable-pip-version-check pytest
)
( # step: Compile every stage dispatcher and the downstream phase machine
set -e
set -euo pipefail
for f in 59-anthology-engine/scripts/stage_s*.py; do
  python3 -m py_compile "$f"
done
python3 -m py_compile 54-anthology-writer/run_anthology.py
python3 -m py_compile 59-anthology-engine/tests/test_stage_run_dir_shared.py
echo "compile OK"
)
( # step: Shared run-directory invariant + Skill 54 P0-INTAKE in both directions
set -e
python3 59-anthology-engine/tests/test_stage_run_dir_shared.py
)
( # step: S9 runner suite (its seeding path is the same invariant)
set -e
python3 -m pytest 59-anthology-engine/tests/test_s9_assembly_runner_confirm_order.py -q
)

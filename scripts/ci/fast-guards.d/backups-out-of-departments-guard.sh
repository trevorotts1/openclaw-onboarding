#!/usr/bin/env bash
# Backup folders must live in the box's ONE central backup folder, never inside the department
# tree, and only the last 3 runs per tool are kept (2026-10-29 owner fix). Added after the CIO002
# fold, so there is no old workflow behind it; the filter lives in scripts/ci/fast-guards.json.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check every file in the blast radius
set -e
bash -n update-skills.sh
bash -n scripts/apply-u004-phase2.sh
bash -n 32-command-center-setup/scripts/backfill-dept-agent-personalization.sh
bash -n tests/unit/backups-out-of-departments.test.sh
bash -n 23-ai-workforce-blueprint/scripts/test-phantom-dept-collision-gate.sh
python3 -m py_compile shared-utils/central_backup.py 23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py
)
( # step: Backups leave the department folders, last 3 kept, second run a no-op, five mutants caught
set -e
bash tests/unit/backups-out-of-departments.test.sh
)
( # step: reconcile-legacy-tree archives to the central folder, not beside departments/
set -e
bash 23-ai-workforce-blueprint/scripts/test-phantom-dept-collision-gate.sh
)

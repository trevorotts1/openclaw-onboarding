#!/usr/bin/env bash
# One shared rulebook: AGENTS.md / TOOLS.md / USER.md on every agent workspace are
# real-file copies of the box's one master, synced from agents.entries, agents.list,
# agents.defaults and the scan, with backup and vendored trees left alone.
# Behavioural fixture-box test plus the neighbouring unify tests, so a change to the
# candidate set, the skip list, the create-missing rule or QC check 9.9 cannot land red.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check
set -e -o pipefail
bash -n install.sh
bash -n update-skills.sh
bash -n scripts/qc-system-integrity.sh
bash -n tests/unit/shared-core-entries-sync.test.sh
bash -n tests/unit/link-shared-tools-create.test.sh
python3 -m py_compile 23-ai-workforce-blueprint/scripts/shared_core_copy.py
python3 -m py_compile 23-ai-workforce-blueprint/scripts/create_role_workspaces.py
echo "syntax OK"
)
( # step: Fixture box (entries + command-center + backup + vendored trees), mutation proof, QC 9.9
set -e -o pipefail
bash tests/unit/shared-core-entries-sync.test.sh
)
( # step: Registered workspaces get all three files (RRS001 widened)
set -e -o pipefail
bash tests/unit/link-shared-tools-create.test.sh
)
( # step: Role folders keep the U053 disposition (no AGENTS.md, real TOOLS/USER copies)
set -e -o pipefail
cd 23-ai-workforce-blueprint/scripts
python3 test_role_workspace_symlinks.py
)

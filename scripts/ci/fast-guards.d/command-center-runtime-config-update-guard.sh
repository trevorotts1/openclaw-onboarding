#!/usr/bin/env bash
# Folded from .github/workflows/command-center-runtime-config-update-guard.yml (job "Local fixture reconciliation"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax checks
set -e
bash -n update-skills.sh
bash -n tests/unit/update-command-center-runtime-config.test.sh
python3 -m py_compile shared-utils/reconcile_command_center_runtime.py
)
( # step: Update-path fixtures
set -e
bash tests/unit/update-command-center-runtime-config.test.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/refresh-stale-roles-retirement-guard.yml (job "STALE-role/sop/dept drain — retirement vs genuinely-missing discrimination"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Syntax checks
set -e
set -euo pipefail
bash -n tests/unit/refresh-stale-roles.test.sh
python3 -m py_compile 23-ai-workforce-blueprint/scripts/refresh-stale-roles.py
python3 -m py_compile 23-ai-workforce-blueprint/scripts/canonical_decline.py
python3 -m py_compile 23-ai-workforce-blueprint/scripts/department-floor.py
)
( # step: Fixture regression suite (10 pre-existing scenarios + 6 retirement-discrimination scenarios)
set -e
bash tests/unit/refresh-stale-roles.test.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/provisioning-completeness-gate-guard.yml (job "VERSION+BRANDING+DEPARTMENTS+ROLE-FLOOR+PERSONAS gate the roll verdict (no false-FAIL)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax check (runner + fleet-refresh.sh)
set -e -o pipefail
set -euo pipefail
python3 -m py_compile shared-utils/fleet_refresh_runner.py
bash -n scripts/fleet-refresh.sh
echo "syntax OK"
)
( # step: Provisioning-completeness gate suite (fixtures; FAIL-before/PASS-after)
set -e -o pipefail
set -euo pipefail
python3 tests/unit/provisioning-completeness-gate.test.py -v
echo "provisioning-completeness-gate-guard: PASS"
)

#!/usr/bin/env bash
# Folded from .github/workflows/one-front-door-full-path-guard.yml (job "every update route runs onboarding + 999 + CC + repair runner + health gate"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the blast radius
set -e -o pipefail
set -euo pipefail
bash -n update-skills.sh
bash -n force-update.sh
bash -n scripts/weekly-full-update.sh
bash -n scripts/fleet-refresh.sh
bash -n shared-utils/lib-frontdoor.sh
bash -n tests/unit/one-front-door-full-path.test.sh
python3 -m py_compile shared-utils/oct4_frontdoor.py
)
( # step: Run the one-front-door full-path suite (includes the stage self-test)
set -e -o pipefail
set -euo pipefail
bash tests/unit/one-front-door-full-path.test.sh
python3 shared-utils/oct4_frontdoor.py --selftest
echo "one-front-door-full-path-guard: PASS"
)

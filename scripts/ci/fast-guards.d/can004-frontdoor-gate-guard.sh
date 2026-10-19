#!/usr/bin/env bash
# CAN004: the front-door stage must name a failing health-gate item (never an opaque
# 'module errored'), and the gate must agree with repair-directors-doctrine on role-less departments.
set -euo pipefail
cd "$GITHUB_WORKSPACE"
bash -n shared-utils/lib-frontdoor.sh
bash -n scripts/health/library-gate-check.sh
python3 -m py_compile shared-utils/oct4_frontdoor.py
bash tests/unit/frontdoor-gate-fail-not-module-error.test.sh
bash tests/unit/gate-repair-empty-department.test.sh
echo "can004-frontdoor-gate-guard: PASS"

#!/usr/bin/env bash
# Folded from .github/workflows/cc-company-id-registry-repair-guard.yml (job "Both copies of the company id are repaired, on every install path"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run the registry-repair regression suite (+ in-suite mutation proof)
set -e -o pipefail
set -euo pipefail
bash tests/unit/cc-company-id-registry-repair.test.sh
echo "cc-company-id-registry-repair-guard: PASS"
)

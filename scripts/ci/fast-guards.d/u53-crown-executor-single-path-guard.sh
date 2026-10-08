#!/usr/bin/env bash
# Folded from .github/workflows/u53-crown-executor-single-path-guard.yml (job "D5 call sites stay thin wrappers; build+restart stays owned by the crowned executor"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run U53/D-HL-3 crown-executor single-path regression suite
set -e -o pipefail
set -euo pipefail
bash tests/probe/test-u53-hl-u68-crown-executor-single-path.sh
echo "u53-crown-executor-single-path-guard: PASS"
)

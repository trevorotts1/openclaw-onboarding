#!/usr/bin/env bash
# Folded from .github/workflows/wire-no-match-guard.yml (job "Grep no-match-abort regression guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run wire-no-match-completes tests
set -e
chmod +x tests/unit/wire-no-match-completes.test.sh
bash tests/unit/wire-no-match-completes.test.sh
)

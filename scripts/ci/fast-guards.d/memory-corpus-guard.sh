#!/usr/bin/env bash
# Folded from .github/workflows/memory-corpus-guard.yml (job "Memory-bloat corpus-placement guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run memory-corpus-no-defaults-extrapaths guard
set -e
chmod +x tests/unit/memory-corpus-no-defaults-extrapaths.test.sh
bash tests/unit/memory-corpus-no-defaults-extrapaths.test.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/presentation-deps-gate.yml (job "Presentation-deps install + QC hard-fail guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run presentation-deps-gate test
set -e
chmod +x tests/unit/presentation-deps-gate.test.sh
bash tests/unit/presentation-deps-gate.test.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/presentation-type-contract-guard.yml (job "Two-field presentation_type contract (U059)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Presentation type contract guard
set -e -o pipefail
chmod +x tests/unit/presentation-type-contract.test.sh
bash tests/unit/presentation-type-contract.test.sh
)

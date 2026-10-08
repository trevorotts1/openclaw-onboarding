#!/usr/bin/env bash
# Folded from .github/workflows/fleet-standing-fail-open-guard.yml (job "Fleet-standing gate stays fail-open (only an explicit blocked verdict may stop an update)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run fleet-standing-gate fail-open regression suite
set -e -o pipefail
set -euo pipefail
bash tests/unit/fleet-standing-gate.test.sh
echo "fleet-standing-fail-open-guard: PASS"
)

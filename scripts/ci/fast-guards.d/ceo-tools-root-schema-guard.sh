#!/usr/bin/env bash
# Folded from .github/workflows/ceo-tools-root-schema-guard.yml (job "sessions/agentToAgent must be on ROOT tools, never per-agent"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run CEO tool-gate self-test (incl. section M root-schema + self-heal)
set -e -o pipefail
set -euo pipefail
bash scripts/test-ceo-tool-gate.sh
echo "ceo-tools-root-schema-guard: PASS — sessions/agentToAgent stay on ROOT tools; self-heal verified."
)

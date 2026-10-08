#!/usr/bin/env bash
# Folded from .github/workflows/skill-manifest-reaper-guard.yml (job ".skill-manifest.json stays dead; .onboarding-content-manifest.json stays authoritative"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the touched scripts
set -e -o pipefail
set -euo pipefail
bash -n install.sh
bash -n update-skills.sh
bash -n scripts/test-skill-manifest-reaper.sh
)
( # step: Assert the dead writer is not resurrected
set -e -o pipefail
set -euo pipefail
if [ -e scripts/generate-manifest.sh ]; then
  echo "REGRESSION: scripts/generate-manifest.sh is back. It is an orphan with no callers."
  exit 1
fi
echo "scripts/generate-manifest.sh: still deleted"
)
( # step: Run the reaper fixture test suite
set -e -o pipefail
set -euo pipefail
bash scripts/test-skill-manifest-reaper.sh
echo "skill-manifest-reaper-guard: PASS"
)

#!/usr/bin/env bash
# Folded from .github/workflows/stuck-build-park-guard.yml (job "Stuck-build PARK loop guard (durable park + bounded resume cron)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the touched scripts (bash -n)
set -e
set -euo pipefail
for f in \
  23-ai-workforce-blueprint/scripts/resume-workforce-build.sh \
  scripts/ensure-pipeline-crons.sh \
  scripts/unpark-build.sh \
  06-ghl-install-pages/tools/browser_manager.sh; do
  bash -n "$f"
  echo "bash -n OK: $f"
done
)
( # step: Run bounded-workforce-build-resume guard
set -e
chmod +x tests/unit/bounded-workforce-build-resume.test.sh
bash tests/unit/bounded-workforce-build-resume.test.sh
)

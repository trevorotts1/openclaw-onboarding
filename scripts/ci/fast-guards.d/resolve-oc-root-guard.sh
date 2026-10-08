#!/usr/bin/env bash
# Folded from .github/workflows/resolve-oc-root-guard.yml (job "Shared resolver equivalence + wiring"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax checks (resolver + every wired script)
set -e
set -euo pipefail
for f in \
  shared-utils/resolve-oc-root.sh \
  tests/unit/resolve-oc-root.test.sh \
  tests/unit/build-state-path-resolution.test.sh \
  32-command-center-setup/scripts/run-full-install.sh \
  update-skills.sh \
  37-zhc-closeout/scripts/run-closeout.sh \
  37-zhc-closeout/scripts/resume-closeout-cron.sh \
  37-zhc-closeout/scripts/fleet-stuck-clients.sh \
  23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh \
  23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh \
  32-command-center-setup/scripts/backfill-per-dept-healer.sh \
  32-command-center-setup/scripts/materialize-dept-agents.sh; do
  bash -n "$f"
done
)
( # step: Resolver equivalence + wiring test
set -e
bash tests/unit/resolve-oc-root.test.sh
)
( # step: Build-state path resolution (the workspace that HAS the file wins)
set -e
bash tests/unit/build-state-path-resolution.test.sh
)

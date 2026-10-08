#!/usr/bin/env bash
# Folded from .github/workflows/workforce-build-pipeline-guard.yml (job "Interview -> build -> closeout pipeline guard (no silent strands)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Syntax-check the pipeline scripts (bash -n)
set -e
set -euo pipefail
for f in \
  23-ai-workforce-blueprint/scripts/resume-workforce-build.sh \
  23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh \
  23-ai-workforce-blueprint/scripts/update-interview-state.sh \
  37-zhc-closeout/scripts/resume-closeout-cron.sh; do
  bash -n "$f"
  echo "bash -n OK: $f"
done
)
( # step: Resume-cron guard (belt contract, vocabulary, QC eligibility, routing, send-is-not-a-turn)
set -e
chmod +x tests/unit/bounded-workforce-build-resume.test.sh
bash tests/unit/bounded-workforce-build-resume.test.sh
)
( # step: Closeout-watchdog guard (blind-spot classes + recovery-lane detection)
set -e
chmod +x tests/unit/closeout-watchdog-stuck-classes.test.sh
bash tests/unit/closeout-watchdog-stuck-classes.test.sh
)
( # step: Closeout-belt guard (never route internal traffic to the client; pause control is real)
set -e
chmod +x tests/unit/closeout-resume-cron-routing.test.sh
bash tests/unit/closeout-resume-cron-routing.test.sh
)

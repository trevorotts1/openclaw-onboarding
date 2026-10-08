#!/usr/bin/env bash
# Folded from .github/workflows/bounded-resume-cron-guard.yml (job "Bounded onboarding-resume cron guard (v12.6.1)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run bounded-resume-cron tests
set -e
chmod +x tests/unit/bounded-resume-cron.test.sh
bash tests/unit/bounded-resume-cron.test.sh
)
( # step: Run update-skills resume-cron tests (idempotency + no-client-channel + seed arg-order)
set -e
chmod +x tests/unit/update-skills-resume-cron.test.sh
bash tests/unit/update-skills-resume-cron.test.sh
)

#!/usr/bin/env bash
# Folded from .github/workflows/social-cron-migration-guard.yml (job "35->57 cron migration guard (atomic, idempotent, config-gated)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run social-cron-migration tests
set -e
chmod +x tests/unit/social-cron-migration.test.sh
bash tests/unit/social-cron-migration.test.sh
)

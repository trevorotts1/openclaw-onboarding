#!/usr/bin/env bash
# Folded from .github/workflows/cron-owner-chat-guard.yml (job "Cron owner-chat operator-rejection guard"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Run cron-owner-chat-guard tests
set -e
chmod +x tests/unit/cron-owner-chat-guard.test.sh
bash tests/unit/cron-owner-chat-guard.test.sh
)
( # step: Run no-operator-comingle-template guard
set -e
chmod +x tests/unit/no-operator-comingle-template.test.sh
bash tests/unit/no-operator-comingle-template.test.sh
)

#!/usr/bin/env bash
set -euo pipefail
cd "$GITHUB_WORKSPACE"
bash scripts/test-d18-d19-npm-ci-node-and-cron-agent-rebind.sh
bash 70-lean-core-file-system/tests/test-install-weekly-cron.sh
echo "d18-d19-npm-ci-node-and-cron-agent-rebind-guard: PASS"

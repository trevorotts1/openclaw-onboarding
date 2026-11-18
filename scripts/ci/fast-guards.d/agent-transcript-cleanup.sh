#!/usr/bin/env bash
# Agent transcript cleanup: the daily prune of old session windows in each agent database
# (archive first, delete in batches, vacuum) and the cron that runs it.
# The tests build fixture databases and run the cron registration and wrapper hermetically.
set -euo pipefail
cd "$GITHUB_WORKSPACE"
bash -n scripts/agent-transcript-cleanup.sh
python3 -m py_compile scripts/agent-transcript-cleanup.py
python3 -I tests/unit/agent-transcript-cleanup.test.py
bash tests/unit/agent-transcript-cleanup-cron.test.sh
echo "agent-transcript-cleanup: PASS"

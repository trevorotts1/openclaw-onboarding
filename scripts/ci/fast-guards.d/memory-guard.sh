#!/usr/bin/env bash
# Memory guard: the nightly memory-search key check (backup chain: original provider,
# OpenRouter nemotron, Gemini), the idle-worker check, and the cron that runs them.
# The test runs the python self-test, the cron registration and the wrapper hermetically.
set -euo pipefail
cd "$GITHUB_WORKSPACE"
bash -n scripts/memory-guard.sh
python3 -m py_compile scripts/memory-guard.py
bash tests/unit/memory-guard.test.sh
echo "memory-guard: PASS"

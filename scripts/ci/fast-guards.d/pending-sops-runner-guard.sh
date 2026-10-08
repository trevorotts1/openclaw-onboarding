#!/usr/bin/env bash
# Folded from .github/workflows/pending-sops-runner-guard.yml (job "PENDING how-tos are queued and filled, never skipped"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: PENDING SOPs runner
set -e
python3 tests/unit/test_pending_sops_runner.py
)

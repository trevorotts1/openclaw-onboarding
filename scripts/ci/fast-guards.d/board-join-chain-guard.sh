#!/usr/bin/env bash
# Folded from .github/workflows/board-join-chain-guard.yml (job "chosen == provisioned == displayed (58 assertions)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Run the C-series board-join prover
set -e -o pipefail
bash 23-ai-workforce-blueprint/scripts/test-board-join-chain.sh
)
( # step: Stray role-library template trees WARN, chosen gaps still drift
set -e
python3 tests/unit/test_board_join_stray_template_depts.py
)

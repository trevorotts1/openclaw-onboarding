#!/usr/bin/env bash
# Folded from .github/workflows/owner-sends-hold-guard.yml (job "Owner sends held on every path; board lanes under one company"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Install jq
set -e
command -v jq || sudo apt-get install -y jq
)
( # step: Owner-sends hold (welcome, gate, celebration, closeout paths)
set -e
python3 tests/unit/test_owner_sends_hold.py
)
( # step: Board company (duplicate row, default queue, repair command)
set -e
python3 tests/unit/test_board_company_repair.py
)
( # step: Structural 'default' lane gets no head agent and no departments/default
set -e
python3 tests/unit/test_no_department_for_default_lane.py
)
( # step: Starter tasks only after closeout, never on an update roll
set -e
bash tests/unit/test_starter_tasks_gate.sh
)

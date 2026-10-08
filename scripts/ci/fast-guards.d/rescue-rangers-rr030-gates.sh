#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr030-gates.yml (job "RR-030 gates (battery + negatives + concurrency + runtimes)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Shell syntax gates
set -e
bash -n scripts/rescue-rangers-harness.sh
bash -n scripts/rr-triage.sh
bash -n shared-utils/oc-env-descriptor.sh
bash -n "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/verify.sh"
)
( # step: Python syntax gates
set -e
python3 -m py_compile "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue_cc_board.py"
python3 -m py_compile "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue_ledger.py"
)
( # step: Full offline battery (UNIT + CONTRACT + INSTALLED + mutation drills)
set -e
bash "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/verify.sh"
)
( # step: Harness hides-nothing proofs
set -e
bash tests/unit/rr030-harness-hides-nothing.test.sh
)
( # step: Board self-test fail-only proofs
set -e
python3 tests/unit/rr030-board-selftest-failsonly.test.py
)
( # step: Triage self-test fail-only proofs
set -e
bash tests/unit/rr030-triage-selftest-failsonly.test.sh
)
( # step: RR-029 QC cases (absent table, permissions, history, polls, retry loop, providers, targets, identity)
set -e
bash tests/unit/rr029-triage-qc-cases.test.sh
)
( # step: RR-029 descriptor resolves one exact target and app readiness
set -e
bash tests/unit/rr029-descriptor-target.test.sh
)
( # step: Staging persistence concurrency gate
set -e
python3 tests/unit/rr030-staging-ledger-concurrency.test.py
)
( # step: Required-runtimes gate (node absence must FAIL)
set -e
bash tests/unit/rr030-verify-required-runtimes.test.sh
)

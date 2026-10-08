#!/usr/bin/env bash
# Folded from .github/workflows/prove-zhe-cc-db-agents-entries-guard.yml (job "prove-zhe measures the live board and roster"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
export OPENCLAW_PLATFORM='mac'
( # step: Install pytest
set -e
python3 -m pip install --quiet --disable-pip-version-check pytest
)
( # step: CC DB / agents.entries / lane regression tests
set -e
python3 -m pytest -q tests/unit/test_prove_zhe_cc_db_and_agents_entries.py
)
( # step: STANDARD_READY selftest
set -e
python3 23-ai-workforce-blueprint/scripts/prove-zhe.py --standard-ready-selftest
)
( # step: Web-parity selftest
set -e
python3 23-ai-workforce-blueprint/scripts/prove-zhe.py --web-parity-selftest
)

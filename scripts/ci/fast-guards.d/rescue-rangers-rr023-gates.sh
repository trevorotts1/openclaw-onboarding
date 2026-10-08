#!/usr/bin/env bash
# Folded from .github/workflows/rescue-rangers-rr023-gates.yml (job "RR-023 gates (importer + regression)"). Generated once by the CIO002 fold; edit freely.
set -e
cd "$GITHUB_WORKSPACE"
( # step: Python syntax gates
set -e
python3 -m py_compile "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/migrate-rescue-staticdata.py"
python3 -m py_compile "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/rescue_ledger.py"
)
( # step: Importer self-test (drill)
set -e
RR_LEDGER_DRILL=1 python3 "23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/migrate-rescue-staticdata.py" --self-test
)
( # step: RR-023 ONB QC battery (37 checks)
set -e
python3 tests/unit/rescue-migration-rr023.test.py
)
( # step: RR-017 regression (contract untouched)
set -e
python3 tests/unit/rescue-contract-rr017.test.py
)
